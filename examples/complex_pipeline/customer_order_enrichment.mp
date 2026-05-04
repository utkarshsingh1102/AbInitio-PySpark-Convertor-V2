<?xml version="1.0" encoding="UTF-8"?>
<graph name="customer_order_enrichment" version="2.0">

  <!-- ============================================================ -->
  <!-- PARAMETERS                                                    -->
  <!-- ============================================================ -->
  <parameters>
    <param name="INPUT_CUSTOMERS"   value="/data/input/customers.csv"          />
    <param name="INPUT_ORDERS"      value="/data/input/orders.csv"             />
    <param name="OUTPUT_HIGH_VALUE" value="/data/output/high_value_orders"     />
    <param name="OUTPUT_STANDARD"   value="/data/output/standard_orders"       />
    <param name="OUTPUT_AUDIT"      value="/data/output/audit_log"             />
    <param name="HIGH_VALUE_THRESHOLD" value="1000.00"                         />
    <param name="DOP"               value="4"                                  />
  </parameters>

  <!-- ============================================================ -->
  <!-- INPUT COMPONENTS                                              -->
  <!-- ============================================================ -->

  <component id="node_01" name="CustomerInput" type="InputFile">
    <property name="filename"    value="${INPUT_CUSTOMERS}" />
    <property name="file_format" value="delimited"         />
    <property name="delimiter"   value=","                 />
    <property name="has_header"  value="true"              />
    <property name="schema"      value="customer.dml"      />
    <port name="out" type="output" />
  </component>

  <component id="node_02" name="OrderInput" type="InputFile">
    <property name="filename"    value="${INPUT_ORDERS}"   />
    <property name="file_format" value="delimited"         />
    <property name="delimiter"   value=","                 />
    <property name="has_header"  value="true"              />
    <property name="schema"      value="order.dml"         />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Normalize Customers                                 -->
  <!-- Uppercase names, parse signup_date, add country_code         -->
  <!-- ============================================================ -->

  <component id="node_03" name="NormalizeCustomer" type="Reformat">
    <property name="transform_file" value="normalize_customer.xfr" />
    <property name="schema"         value="customer_normalized.dml" />
    <port name="in"  type="input"  source="node_01.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Normalize Orders                                    -->
  <!-- Cast amount, derive order_month, flag nulls                  -->
  <!-- ============================================================ -->

  <component id="node_04" name="NormalizeOrder" type="Reformat">
    <property name="transform_file" value="normalize_order.xfr" />
    <property name="schema"         value="order_normalized.dml" />
    <port name="in"  type="input"  source="node_02.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- JOIN: Enrich Orders with Customer Data                        -->
  <!-- Inner join on customer_id                                    -->
  <!-- ============================================================ -->

  <component id="node_05" name="JoinCustomerOrder" type="Join">
    <property name="join_type"    value="inner"        />
    <property name="join_key"     value="customer_id"  />
    <property name="left_input"   value="node_03.out"  />
    <property name="right_input"  value="node_04.out"  />
    <property name="schema"       value="enriched_order.dml" />
    <port name="in_left"  type="input" source="node_03.out" />
    <port name="in_right" type="input" source="node_04.out" />
    <port name="out"      type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Enrich Joined Record                               -->
  <!-- Compute total_with_tax, loyalty_tier, days_since_signup      -->
  <!-- ============================================================ -->

  <component id="node_06" name="EnrichRecord" type="Reformat">
    <property name="transform_file" value="enrich_record.xfr" />
    <property name="schema"         value="enriched_order.dml" />
    <port name="in"  type="input"  source="node_05.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- FILTER: High-Value Orders  (order_amount > 1000)             -->
  <!-- ============================================================ -->

  <component id="node_07" name="FilterHighValue" type="Filter">
    <property name="condition"      value="order_amount > ${HIGH_VALUE_THRESHOLD}" />
    <property name="transform_file" value="filter_high_value.xfr" />
    <port name="in"  type="input"  source="node_06.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- FILTER: Standard Orders  (order_amount <= 1000)              -->
  <!-- ============================================================ -->

  <component id="node_08" name="FilterStandard" type="Filter">
    <property name="condition"      value="order_amount <= ${HIGH_VALUE_THRESHOLD}" />
    <property name="transform_file" value="filter_standard.xfr" />
    <port name="in"  type="input"  source="node_06.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Apply Loyalty Discount for High-Value              -->
  <!-- ============================================================ -->

  <component id="node_09" name="ApplyLoyaltyDiscount" type="Reformat">
    <property name="transform_file" value="apply_discount.xfr" />
    <property name="schema"         value="enriched_order.dml" />
    <port name="in"  type="input"  source="node_07.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- AGGREGATE: Summarize Standard Orders by Customer             -->
  <!-- ============================================================ -->

  <component id="node_10" name="AggregateStandard" type="Aggregate">
    <property name="group_by"   value="customer_id, order_month"       />
    <property name="aggregates" value="sum(order_amount):monthly_spend, count(order_id):order_count" />
    <property name="schema"     value="standard_summary.dml"           />
    <port name="in"  type="input"  source="node_08.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- OUTPUT COMPONENTS                                             -->
  <!-- ============================================================ -->

  <component id="node_11" name="HighValueOutput" type="OutputFile">
    <property name="filename"    value="${OUTPUT_HIGH_VALUE}" />
    <property name="file_format" value="parquet"              />
    <property name="mode"        value="overwrite"            />
    <port name="in" type="input" source="node_09.out" />
  </component>

  <component id="node_12" name="StandardOutput" type="OutputFile">
    <property name="filename"    value="${OUTPUT_STANDARD}"   />
    <property name="file_format" value="parquet"              />
    <property name="mode"        value="overwrite"            />
    <port name="in" type="input" source="node_10.out" />
  </component>

  <component id="node_13" name="AuditOutput" type="OutputFile">
    <property name="filename"    value="${OUTPUT_AUDIT}"      />
    <property name="file_format" value="parquet"              />
    <property name="mode"        value="append"               />
    <port name="in" type="input" source="node_06.out" />
  </component>

  <!-- ============================================================ -->
  <!-- CONNECTIONS (explicit edge list)                             -->
  <!-- ============================================================ -->

  <connections>
    <edge from="node_01" to="node_03" />   <!-- CustomerInput → NormalizeCustomer    -->
    <edge from="node_02" to="node_04" />   <!-- OrderInput → NormalizeOrder          -->
    <edge from="node_03" to="node_05" />   <!-- NormalizeCustomer → Join (left)      -->
    <edge from="node_04" to="node_05" />   <!-- NormalizeOrder → Join (right)        -->
    <edge from="node_05" to="node_06" />   <!-- Join → EnrichRecord                  -->
    <edge from="node_06" to="node_07" />   <!-- EnrichRecord → FilterHighValue       -->
    <edge from="node_06" to="node_08" />   <!-- EnrichRecord → FilterStandard  (fan-out) -->
    <edge from="node_06" to="node_13" />   <!-- EnrichRecord → AuditOutput     (fan-out) -->
    <edge from="node_07" to="node_09" />   <!-- FilterHighValue → ApplyDiscount      -->
    <edge from="node_08" to="node_10" />   <!-- FilterStandard → AggregateStandard   -->
    <edge from="node_09" to="node_11" />   <!-- ApplyDiscount → HighValueOutput      -->
    <edge from="node_10" to="node_12" />   <!-- AggregateStandard → StandardOutput   -->
  </connections>

</graph>
