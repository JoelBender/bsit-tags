import html
import logging
import re
from typing import Any, Callable

from nicegui import ui

from bacpypes3.primitivedata import (
    BitString,
    Boolean,
    CharacterString,
    Date,
    Double,
    Enumerated,
    Integer,
    Null,
    ObjectIdentifier,
    ObjectType,
    OctetString,
    PropertyIdentifier,
    Real,
    Time,
    Unsigned,
    attr_to_asn1,
)
from bacpypes3.basetypes import (
    DateTime,
    NameValue,
)
from bacpypes3.vendor import ASHRAE_vendor_info

from rdflib import Graph, BNode, Literal, Namespace, URIRef, RDF, RDFS, XSD
from bacpypes3.rdf.util import BACnetNS, atomic_encode, sequence_to_graph

_logger = logging.getLogger(__name__)

default_prefixes: dict[str, Namespace] = {
    "rdf": RDF,
    "rdfs": RDFS,
    "xsd": XSD,
}
prefixes: dict[str, Namespace] = {}

# optional suffix for repeating tags
uniqueness_suffix_re = re.compile(r"[(][0-9]+[)]$")

def name_to_uri(name: str) -> URIRef:
    """
    Convert a name to a URIRef, handling prefixes and blank nodes.
    """
    global base_name, prefixes

    if ":" in name:
        prefix, suffix = name.split(":", 1)

        if prefix == "_":
            return BNode(suffix)
        if prefix in prefixes:
            return prefixes[prefix][suffix]
        raise ValueError(f"undefined prefix: {prefix}")

    return URIRef(base_name + name)


def _cast(datatype: type) -> Callable[[str], Any]:
    """
    Return a function that casts a string value to the specified datatype.
    Handles special cases for None and Null types.  The conversion functions
    for the other datatypes will raise ValueError if the value is invalid,
    which is used for validation in the table.
    """

    def _cast_fn(value: str) -> Any:
        if datatype is None:
            if value == "":
                return None
            else:
                raise ValueError("Value must be empty string")

        if datatype is Null:
            if value == "":
                return Null(())
            else:
                raise ValueError("Value must be empty string")

        return datatype(value)

    return _cast_fn


datatype_cast = {
    "None": _cast(None),
    "Null": _cast(Null),
    "Boolean": _cast(Boolean),
    "Integer": _cast(Integer),
    "Real": _cast(Real),
    "Double": _cast(Double),
    "CharacterString": _cast(CharacterString),
    # "OctetString": _cast(OctetString),
    "BitString": _cast(BitString),
    "Enumerated": _cast(Enumerated),
    "ObjectIdentifier": _cast(ObjectIdentifier),
    "ObjectType": _cast(ObjectType),
    "PropertyIdentifier": _cast(PropertyIdentifier),
    "Date": _cast(Date),
    "Time": _cast(Time),
    "Unsigned": _cast(Unsigned),
    "DateTime": _cast(DateTime),
}
datatype_options = list(datatype_cast.keys())


class ObjectPropertyTable:
    table: Any
    table_data: list[dict[str, Any]]
    next_id: int
    on_change: Callable[["ObjectPropertyTable"], None] | None

    def __init__(
        self,
        label: str,
        table_data: list[dict[str, Any]],
        on_change: Callable[["ObjectPropertyTable"], None] | None = None,
    ):
        # Table data by reference
        self.table_data = table_data
        self.on_change = on_change

        # Rows need a unique ID for tracking.
        if not table_data:
            self.next_id = 0
        else:
            self.next_id = max(row["id"] for row in table_data) + 1

        with ui.row().classes("w-full justify-between items-center"):
            ui.label(label).style("font-size: 1.2em; font-weight: bold")
            ui.button("Add Row", on_click=self.add_row, icon="add").props(
                "color=primary"
            )

        # Define table columns
        columns = [
            {
                "name": "name",
                "label": "Name",
                "field": "name",
                "align": "left",
                "headerStyle": "width: 100px",
            },
            {
                "name": "value",
                "label": "Value",
                "field": "value",
                "align": "left",
                "headerStyle": "width: 100px",
            },
            {
                "name": "datatype",
                "label": "Datatype",
                "field": "datatype",
                "align": "left",
                "headerStyle": "width: 150px",
            },
            {
                "name": "actions",
                "label": "",
                "field": "actions",
                "align": "center",
                "headerStyle": "width: 30px",
            },
        ]

        # Validate the rows initially to set any invalid flags
        for row in self.table_data:
            self.validate_row(row)

        # Create the table
        self.table = ui.table(
            columns=columns,
            rows=table_data,
            row_key="id",
        ).classes("w-full")

        _logger.debug(f"{self.table.id = }")

        # Add custom slot for editable cells
        self.table.add_slot(
            "body",
            r"""
            <q-tr :props="props" :data-row-key="props.row.id" :style="props.row.invalid ? 'background-color: pink; color: white;' : ''">
                <q-td key="name" :props="props">
                    <input 
                        :value="props.row.name"
                        @input="e => { props.row.name = e.target.value; $parent.$emit('cell-change', props.row.id, 0, e.target.value) }"
                        @blur="() => $parent.$emit('cell-blur', props.row.id, 0)"
                        @focus="e => e.target.select()"
                        class="q-field__native"
                        style="border: none; outline: none; width: 100%;"
                    />
                </q-td>
                <q-td key="value" :props="props">
                    <input 
                        :value="props.row.value"
                        @input="e => { props.row.value = e.target.value; $parent.$emit('cell-change', props.row.id, 1, e.target.value) }"
                        @blur="() => $parent.$emit('cell-blur', props.row.id, 1)"
                        @focus="e => e.target.select()"
                        class="q-field__native"
                        style="border: none; outline: none; width: 100%;"
                    />
                </q-td>
                <q-td key="datatype" :props="props">
                    <q-select 
                        dense 
                        v-model="props.row.datatype" 
                        :options="""
            + '"'
            + str(datatype_options)
            + '"'
            + r"""
                        @update:model-value="() => $parent.$emit('cell-change', props.row.id, 2, props.row.datatype)"
                        @blur="() => $parent.$emit('cell-blur', props.row.id, 2)"
                        borderless
                    />
                </q-td>
                <q-td key="actions" :props="props">
                    <q-btn 
                        flat 
                        dense 
                        round 
                        icon="delete" 
                        color="negative"
                        @click="() => $parent.$emit('delete-row', props.row.id)"
                    />
                </q-td>
            </q-tr>
        """,
        )

        self.table.on("cell-change", self.on_cell_change)
        self.table.on("cell-blur", self.on_cell_blur)
        self.table.on("delete-row", self.on_delete_row)

    # Handle cell changes (update data silently without updating markdown)
    def on_cell_change(self, e):
        _logger.debug(f"on_cell_change: {e.args}")
        row_id = e.args[0]
        col_idx = e.args[1]
        new_value = e.args[2]

        # Find the row with the matching ID and update it
        for row in self.table_data:
            if row["id"] == row_id:
                if col_idx == 0:
                    row["name"] = new_value
                elif col_idx == 1:
                    row["value"] = new_value
                elif col_idx == 2:
                    row["datatype"] = new_value

                # validate the row after any change to update the invalid flag and styling
                self.validate_row(row)

                if row["invalid"]:
                    background_color = "pink"
                    text_color = "white"
                else:
                    background_color = ""
                    text_color = ""

                # Update the table to reflect styling changes using JavaScript
                # Find the row by data-row-key attribute and update its style directly
                java_script = f"""
                    document.querySelectorAll('#c{self.table.id} tr').forEach(tr => {{
                        const rowKey = tr.getAttribute('data-row-key');
                        if (rowKey === '{row_id}') {{
                            tr.style.backgroundColor = '{background_color}';
                            tr.style.color = '{text_color}';
                        }}
                    }});
                """

                ui.run_javascript(java_script)

                break

        # Update markdown immediately for dropdown (col_idx == 2), wait for blur for text inputs
        if col_idx == 2:
            if self.on_change:
                self.on_change(self)

    def on_cell_blur(self, e):
        _logger.debug(f"on_cell_blur: {e.args}")
        if self.on_change:
            self.on_change(self)

    def on_delete_row(self, e):
        _logger.debug(f"on_delete_row: {e.args}")
        row_id = e.args if isinstance(e.args, int) else e.args[0]
        self.delete_row(row_id)

    def add_row(self):
        """Add a new row to the table with default values"""
        new_row = {
            "id": self.next_id,
            "name": "tag-name",
            "value": "tag-value",
            "datatype": "CharacterString",
        }
        self.next_id += 1

        self.table_data.append(new_row)
        self.table.rows = self.table_data
        self.table.update()

        if self.on_change:
            self.on_change(self)

    def delete_row(self, row_id):
        """Delete a row from the table"""

        # Find and remove the row with the matching ID
        for i, row in enumerate(self.table_data):
            if row["id"] == row_id:
                break
        else:
            _logger.debug(f"    - {row_id=} not found")
            return

        self.table_data.pop(i)
        self.table.rows = self.table_data
        self.table.update()

        if self.on_change:
            self.on_change(self)

    def validate_row(self, row: dict[str, Any]) -> bool:
        """Validate a row based on its datatype. Returns True iff valid."""
        _logger.debug(f"Validating row {row['id']}: {row}")

        datatype = row.get("datatype", "")
        value = row.get("value", "")

        try:
            cast_fn = datatype_cast.get(datatype)
            if cast_fn is not None:
                cast_fn(value)
        except (ValueError, TypeError):
            is_valid = False
        else:
            is_valid = True

        # Update row's invalid flag
        if is_valid:
            row["invalid"] = False
        else:
            row["invalid"] = True

        return is_valid


obj_data = [
    {
        "id": 0,
        "name": "object-name",
        "value": "Analog Value 1",
        "datatype": "CharacterString",
    },
    {
        "id": 1,
        "name": "object-identifier",
        "value": "analog-value,1",
        "datatype": "ObjectIdentifier",
    },
    {"id": 2, "name": "object-type", "value": "analog-value", "datatype": "ObjectType"},
]
tag_data = []


def set_code_content(content: str):
    global code_element
    js_code = f"""
        const el = document.getElementById("c{code_element.id}");
        const codePart = el.querySelector('.codehilite pre');
        if (codePart) {{
            codePart.innerHTML = `{content}`;
        }}
    """
    ui.run_javascript(js_code)


def on_table_change(table: ObjectPropertyTable | None):
    _logger.debug(f"on_table_change {table=}")
    global base_name, prefixes

    try:
        obj_type = obj_identifier = None
        for row in obj_data:
            if row["name"] == "object-type":
                obj_type = row["value"]
            if row["name"] == "object-identifier":
                obj_identifier = row["value"]

        if obj_type is None:
            raise ValueError("object-type property is required in object properties")
        if obj_identifier is None:
            raise ValueError(
                "object-identifier property is required in object properties"
            )

        try:
            obj_type_enum = ObjectType(obj_type)
        except ValueError:
            raise ValueError(f"Invalid object-type value: {obj_type}")

        obj_class = ASHRAE_vendor_info.get_object_class(obj_type_enum)
        assert obj_class

        # Get attribute names and map to them from property names
        attribute_names = list(obj_class._elements.keys())
        property_to_attr = dict((attr_to_asn1(attr), attr) for attr in attribute_names)

        # build an instance of the object, set the property values
        sample_obj = obj_class()
        for row in obj_data:
            prop_name = row["name"]
            prop_datatype = row["datatype"]

            cast_fn = datatype_cast[prop_datatype]
            prop_value = cast_fn(row["value"])

            if prop_name not in property_to_attr:
                raise ValueError(
                    f"Property name '{prop_name}' is not an attribute of {obj_type_enum}"
                )

            setattr(sample_obj, property_to_attr[prop_name], prop_value)

        # default base name
        vendor_id = 999
        base_name = None
        id_name = None
        language_name = None

        # reset prefixes to the defaults
        prefixes = default_prefixes.copy()

        g = Graph()
        g.bind("bacnet", BACnetNS)

        # build tags list and a set of statements
        tags = []
        statements = set()
        for i, row in enumerate(tag_data):
            tag_name = row["name"]
            tag_datatype = row["datatype"]

            if not tag_name:
                raise ValueError(f"row {i + 1}: tag name required")

            # cast the tag value according to the specified datatype
            cast_fn = datatype_cast[tag_datatype]
            tag_value = cast_fn(row["value"])
            _logger.debug(
                f"Tag '{tag_name}' casted value: {tag_value} (type: {type(tag_value)})"
            )

            # the tags property is a list of NameValue pairs
            tag = NameValue(name=tag_name)
            if tag_value is not None:
                tag.value = tag_value
            _logger.debug(f"Created tag: {tag}, {tag.name = }, {tag.value = }")

            tags.append(tag)

            if tag_name == "@base":
                if base_name is not None:
                    raise RuntimeError(f"row {i + 1}: @base already specified")
                if not isinstance(tag_value, str):
                    raise TypeError(f"row {i + 1}: @base string expected")

                # strict handling of base IRI
                # if (not tag_value.startswith("<")) or (not tag_value.endswith(">")):
                #    raise ValueError(f"row {i+1}: @base IRIREF expected")

                # generous handling of base IRI
                if tag_value.startswith("<") and tag_value.endswith(">"):
                    tag_value = tag_value[1:-1]

                base_name = tag_value
                continue

            if tag_name == "@id":
                if id_name is not None:
                    raise RuntimeError(f"row {i + 1}: @id already specified")
                if not isinstance(tag_value, str):
                    raise TypeError(f"row {i + 1}: @id string expected")
                id_name = tag_value
                continue

            if tag_name == "@language":
                if language_name is not None:
                    raise RuntimeError(f"row {i + 1}: @language already specified")
                if not isinstance(tag_value, str):
                    raise TypeError(f"row {i + 1}: @language string expected")
                language_name = tag_value
                continue

            if tag_name.startswith("@"):
                raise ValueError(f"row {i + 1}: unrecognized directive '{tag_name}'")

            if tag_name.endswith(":"):
                # trim off the ':' and use as prefix
                tag_name = tag_name[:-1]
                if not isinstance(tag_value, str):
                    raise TypeError(f"row {i + 1}: prefix string value expected")

                # generous handling of prefix IRI
                if tag_value.startswith("<") and tag_value.endswith(">"):
                    tag_value = tag_value[1:-1]

                prefixes[tag_name] = Namespace(tag_value)
                g.namespace_manager.bind(tag_name, URIRef(tag_value))
                continue

            # for regular tags, add to the set of statements
            statements.add((tag_name, tag_value))

        _logger.debug(f"{statements = }\n")

        # set the tags property on the sample object to the list of
        # NameValue pairs
        setattr(sample_obj, "tags", tags)

        # default base name if @base not specified
        if base_name is None:
            base_name = f"http://example.com/vendor/{vendor_id}/"

        # create the subject for the RDF graph, either from @id or a blank
        # node based on object identifier
        s: URIRef
        if id_name:
            s = name_to_uri(id_name)
        else:
            s = BNode(obj_identifier.replace(",", "-"))
        _logger.debug(f"{s = }")

        for tag_name, tag_value in statements:
            language: str | None = language_name
            datatype: URIRef | None = None

            # if there is a trailing suffix for uniqueness, remove it
            tag_name = uniqueness_suffix_re.sub("", tag_name)

            if "@" in tag_name:
                tag_name, language = tag_name.split("@", 1)
            elif "^^" in tag_name:
                tag_name, _datatype = tag_name.split("^^", 1)
                datatype = name_to_uri(_datatype)

            p = name_to_uri(tag_name)
            _logger.debug(f"{p = } {language = } {datatype = }")

            if tag_value is None:
                g.add((s, RDF.type, p))
                continue

            if isinstance(tag_value, str):
                if datatype == XSD.anyURI:
                    if tag_value.startswith("<") and tag_value.endswith(">"):
                        o = URIRef(tag_value[1:-1])
                    else:
                        o = name_to_uri(tag_value)
                else:
                    if datatype == RDF.PlainLiteral:
                        datatype = None

                    o = Literal(tag_value, datatype=datatype, lang=language)
            else:
                o = atomic_encode(g, tag_value)
            _logger.debug(f"{o = }")

            g.add((s, p, o))

        sequence_to_graph(sample_obj, s, g)
        block_content = html.escape(g.serialize(format="turtle"))

    except Exception as e:
        _logger.debug(f"Error: {e}")
        block_content = f"Error: {e}"

    set_code_content(block_content)


# Basic table for regular object properties
obj_table = ObjectPropertyTable(
    "Object Properties", obj_data, on_change=on_table_change
)

# Separate table for tags property
tag_table = ObjectPropertyTable("Tags", tag_data, on_change=on_table_change)

# Label for displaying validation errors
label_element = ui.label("").classes("text-red")

# Area to display the generated RDF/Turtle code
code_element = ui.code("").classes("w-full")

if __name__ in {"__main__", "__mp_main__"}:
    ui.run()
