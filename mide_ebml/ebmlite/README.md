*ebmlite* README
==============

*ebmlite* is a lightweight, "pure Python" library for parsing EBML. It is designed to crawl through EBML files quickly and efficiently, and that's about it. *ebmlite* can also do basic EBML encoding, but more advanced EBML manipulation (e.g. with a proper DOM) are beyond its scope, and are better left to other libraries.

EBML Overview (the short version)
---------------------------------

[EBML](http://matroska-org.github.io/libebml/)  (Extensible Binary Markup Language) is a hierarchical tagged binary format. It bears some functional similarity to XML, although the actual structure differs significantly.

EBML elements consist of a numeric ID, the size of the element, and a payload. The lengths of the ID and size descriptors are variable, using prefix bits to indicate their lengths, a system similar to UTF-8. The mapping of IDs to names and payload data types is done via an external schema.

See the [official specification](http://matroska-org.github.io/libebml/specs.html) for more information.

EBML Schemata
-------------

An EBML file is largely meaningless without a schema that defines its elements. The schema maps element IDs to names and data types; it also describes the structure (e.g. what elements can be children of other elements) and provides additional metadata. *Note: ebmlite does not currently enforce structure.*

*ebmlite* schemata are defined in XML. From these XML files, a `Schema` instance is created; within the `Schema` are `Element` subclasses for each element defined in the XML. Importing an EBML file is done through the `Schema` instance.

```xml
<?xml version="1.0" encoding="utf-8"?>
<Schema>
    <MasterElement name="EBML" id="0x1A45DFA3" mandatory="1" multiple="0">
        <UIntegerElement name="EBMLVersion" id="0x4286" multiple="0" mandatory="1" />
        <UIntegerElement name="EBMLReadVersion" id="0x42F7" multiple="0" mandatory="1"/>
        <UIntegerElement name="EBMLMaxIDLength" id="0x42F2" multiple="0" mandatory="1"/>
        <UIntegerElement name="EBMLMaxSizeLength" id="0x42F3" multiple="0" mandatory="1"/>
        <StringElement name="DocType" id="0x4282" multiple="0" mandatory="1"/>
        <UIntegerElement name="DocTypeVersion" id="0x4287" multiple="0" mandatory="1"/>
        <BinaryElement name="Void" level="-1" id="0xEC" multiple="1"/>
        <BinaryElement name="CRC-32" level="-1" id="0xBF" multiple="0"/>
        <MasterElement name="SignatureSlot" level="-1" id="0x1B538667" multiple="1">
            <UIntegerElement name="SignatureAlgo" id="0x7E8A" multiple="0"/>
            <UIntegerElement name="SignatureHash" id="0x7E9A" multiple="0"/>
            <BinaryElement name="SignaturePublicKey" id="0x7EA5" multiple="0"/>
            <BinaryElement name="Signature" id="0x7EB5" multiple="0"/>
            <MasterElement name="SignatureElements" id="0x7E5B" multiple="0">
                <MasterElement name="SignatureElementList" id="0x7E7B" multiple="1">
                    <BinaryElement name="SignedElement" id="0x6532" multiple="1"/>
                </MasterElement>
            </MasterElement>
        </MasterElement>
    </MasterElement>
    <!-- More definitions would follow... -->
</Schema>
```

```python
from ebmlite import loadSchema
schema = loadSchema('mide.xml')
doc = schema.load('test_file.ebml')
```
