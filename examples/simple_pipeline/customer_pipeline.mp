<?xml version="1.0" encoding="UTF-8"?>
<graph name="customer_pipeline">

  <parameters>
    <param name="INPUT_PATH"  value="data/input/customers.parquet"          />
    <param name="OUTPUT_PATH" value="data/output/customers_filtered.parquet" />
    <param name="MIN_AGE"     value="18"                                     />
  </parameters>

  <component id="node_1" name="Input" type="InputFile">
    <property name="filename"    value="${INPUT_PATH}" />
    <property name="file_format" value="parquet"       />
    <property name="schema"      value="customer"      />
    <port name="out" type="output" />
  </component>

  <component id="node_2" name="Reformat" type="Reformat">
    <property name="transform_file" value="customer_normalize" />
    <property name="schema"         value="customer"           />
    <port name="in"  type="input"  source="node_1.out" />
    <port name="out" type="output" />
  </component>

  <component id="node_3" name="Filter" type="Filter">
    <property name="condition" value="age > ${MIN_AGE}" />
    <property name="schema"    value="customer"        />
    <port name="in"  type="input"  source="node_2.out" />
    <port name="out" type="output" />
  </component>

  <component id="node_4" name="Output" type="OutputFile">
    <property name="filename"    value="${OUTPUT_PATH}" />
    <property name="file_format" value="parquet"        />
    <property name="mode"        value="overwrite"      />
    <port name="in" type="input" source="node_3.out" />
  </component>

  <connections>
    <edge from="node_1" to="node_2"/>
    <edge from="node_2" to="node_3"/>
    <edge from="node_3" to="node_4"/>
  </connections>
</graph>
