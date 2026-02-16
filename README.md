# BSIT Tags

This project is a [NiceGUI](https://nicegui.io/) application for exploring the
translation of the _tags_ property of a BACnet object to RDF.  This is a part
of the BACnet Semantic Interoperability Toolkit (BSIT) for constructing ASHRAE
223 models of HVAC systems.

## Getting Started

Clone the repository and run the application using [uv](https://github.com/astral-sh/uv).

```shell
$ git clone xxxxx
$ cd xxxxx
$ uv run main.py
NiceGUI ready to go on http://localhost:8080, ...
```

Open a web browser to the URL and you will be presented with two tables; the
top table will be for the basic required properties of a BACnet object like
its name, object identifier, and object type, the bottom table will be a list
of `BACnetNameValue` pairs.

Below both tables is a Turtle serialization of the _object graph_ that matches
the object content.  There are other rules in the proposal for the standard for
how context information can be inherited from the tags of a device object and
the subordinate tags of a structured view object that are beyond the scope of
this demonstration.

## Primitive Data Values

This application only supports object properties and tag values that are
BACnet primitive data types and `BACnetDateTime`.  For more details about the
acceptable string values for each datatype refer to the [BACpypes3](https://bacpypes3.readthedocs.io/)
library.

| Datatype | Sample | Notes |
|----------|--------|-------|
| None | (empty string) | 1 |
| Null | (empty string) | 2 |
| Boolean | true, false, set, reset | |
| Integer | 12 | |
| Real | 34.5 | |
| Double | 678.9 | |
| CharacterString | Chilled Water Temperature | |
| BitString | 1;4;5 | 3 |
| Enumerated | 13 | 4 |
| ObjectIdentifier | analog-value,1 | |
| ObjectType | analog-value | 5 |
| PropertyIdentifier | description | 6 |
| Date | 2026-01-2 | 7 |
| Time | 12:34:45 | 7 |
| DateTime | 2026-01-2 12:34:45 | 7 |

### Notes

1. The `None` type indicates that only the `name` is present in the `BACnetNameValue`
   sequence, the optional `value` is not present
2. The `Null` type is the special BACnet NULL value
3. Bit strings are ';' separated integer values for the bits that are set (1).
4. Enumerated values are integers because the ASN.1 names are not available
5. The object type is a specific enumeration, BACpypes3 supports the ASN.1 name
   as well as an integer value
6. The property identifier is also a specific enumeration, see (5)
7. The `Date`, `Time` and `DateTime` datatypes support `*` and other special
   names.

## Tag Name Forms

This is a summary of the forms that tag names can have, they closely match the
same form that Turtle specifies.  For more detailed information see the proposal.

| Directive Tag Name | Description |
|----------|-------------|
| `@base` | Set the base for non-prefixed tag names |
| `@id` | Set the identifier, defaults to `_:object-type-instance` |
| `@language` | Set the default language for strings |


| Tag Name | Description |
|----------|-------------|
| `:` | Minimal prefix declaration |
| `ex:` | Normal prefix declaration |
| `snork` | Non-prefixed name, `@base` applies |
| `ex:snork` | Prefixed name |
| `snork@fr` | Language for a literal |
| `snork^^xsd:short` | Datatype for a literal |
| `snork(1)` | Repeating value |


