<?xml version="1.0" encoding="UTF-8"?>
<graph name="txn_risk_scoring_regulatory" version="2.0">

  <!-- ============================================================ -->
  <!-- PARAMETERS                                                    -->
  <!-- ============================================================ -->
  <parameters>
    <param name="INPUT_TRANSACTIONS"    value="/data/input/transactions.csv"          />
    <param name="INPUT_ACCOUNTS"        value="/data/input/accounts.csv"              />
    <param name="INPUT_RISK_RULES"      value="/data/input/risk_rules.csv"            />
    <param name="OUTPUT_FLAGGED"        value="/data/output/flagged_transactions"     />
    <param name="OUTPUT_CLEAN"          value="/data/output/clean_transactions"       />
    <param name="OUTPUT_REGULATORY"     value="/data/output/regulatory_report"        />
    <param name="OUTPUT_BLOCKED"        value="/data/output/blocked_accounts"         />
    <param name="HIGH_RISK_SCORE"       value="75"                                    />
    <param name="VELOCITY_WINDOW_HOURS" value="24"                                    />
    <param name="LARGE_TXN_THRESHOLD"   value="10000.00"                              />
    <param name="DOP"                   value="8"                                     />
    <param name="REPORT_DATE"           value="2024-01-31"                            />
  </parameters>

  <!-- ============================================================ -->
  <!-- INPUT COMPONENTS  (3 sources)                                 -->
  <!-- ============================================================ -->

  <component id="node_01" name="TransactionInput" type="InputFile">
    <property name="filename"    value="${INPUT_TRANSACTIONS}" />
    <property name="file_format" value="delimited"             />
    <property name="delimiter"   value=","                     />
    <property name="has_header"  value="true"                  />
    <property name="schema"      value="transaction_raw.dml"   />
    <port name="out" type="output" />
  </component>

  <component id="node_02" name="AccountInput" type="InputFile">
    <property name="filename"    value="${INPUT_ACCOUNTS}"    />
    <property name="file_format" value="delimited"             />
    <property name="delimiter"   value=","                     />
    <property name="has_header"  value="true"                  />
    <property name="schema"      value="account_raw.dml"       />
    <port name="out" type="output" />
  </component>

  <!-- Risk rules is a small lookup/dimension table -->
  <component id="node_03" name="RiskRulesInput" type="InputFile">
    <property name="filename"    value="${INPUT_RISK_RULES}"  />
    <property name="file_format" value="delimited"             />
    <property name="delimiter"   value=","                     />
    <property name="has_header"  value="true"                  />
    <property name="schema"      value="risk_rules.dml"        />
    <property name="is_lookup"   value="true"                  />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Normalize Transactions                              -->
  <!-- Cast types, derive txn_hour, flag cross-border               -->
  <!-- ============================================================ -->

  <component id="node_04" name="NormalizeTransaction" type="Reformat">
    <property name="transform_file" value="normalize_transaction.xfr" />
    <property name="schema"         value="transaction_normalized.dml" />
    <port name="in"  type="input"  source="node_01.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Normalize Accounts                                  -->
  <!-- Derive account_age_days, tier, clean country                 -->
  <!-- ============================================================ -->

  <component id="node_05" name="NormalizeAccount" type="Reformat">
    <property name="transform_file" value="normalize_account.xfr" />
    <property name="schema"         value="account_normalized.dml" />
    <port name="in"  type="input"  source="node_02.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- FILTER: Remove CLOSED accounts before join                   -->
  <!-- ============================================================ -->

  <component id="node_06" name="FilterActiveAccounts" type="Filter">
    <property name="condition"      value="account_status != 'CLOSED'" />
    <property name="transform_file" value="filter_active_accounts.xfr" />
    <port name="in"  type="input"  source="node_05.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- FILTER: Remove CANCELLED / TEST transactions                  -->
  <!-- ============================================================ -->

  <component id="node_07" name="FilterValidTransactions" type="Filter">
    <property name="condition"      value="txn_status != 'CANCELLED' and txn_status != 'TEST' and txn_amount > 0" />
    <property name="transform_file" value="filter_valid_transactions.xfr" />
    <port name="in"  type="input"  source="node_04.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- JOIN 1: Enrich Transactions with Account Data                 -->
  <!-- Left join — keep transactions even if account not found       -->
  <!-- ============================================================ -->

  <component id="node_08" name="JoinTxnAccount" type="Join">
    <property name="join_type"    value="left"        />
    <property name="join_key"     value="account_id"  />
    <property name="left_input"   value="node_07.out" />
    <property name="right_input"  value="node_06.out" />
    <property name="schema"       value="txn_account_enriched.dml" />
    <port name="in_left"  type="input" source="node_07.out" />
    <port name="in_right" type="input" source="node_06.out" />
    <port name="out"      type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- JOIN 2: Attach Risk Rule Scores                              -->
  <!-- Left join on txn_type + account_tier (composite key)         -->
  <!-- ============================================================ -->

  <component id="node_09" name="JoinRiskRules" type="Join">
    <property name="join_type"    value="left"                    />
    <property name="join_key"     value="txn_type,account_tier"   />
    <property name="left_input"   value="node_08.out"             />
    <property name="right_input"  value="node_03.out"             />
    <property name="schema"       value="txn_risk_enriched.dml"   />
    <port name="in_left"  type="input" source="node_08.out" />
    <port name="in_right" type="input" source="node_03.out" />
    <port name="out"      type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Compute Velocity Window Features                    -->
  <!-- Rolling 24h txn count and sum per account (window function)  -->
  <!-- ============================================================ -->

  <component id="node_10" name="ComputeVelocity" type="Reformat">
    <property name="transform_file" value="compute_velocity.xfr"        />
    <property name="schema"         value="txn_risk_enriched.dml"        />
    <property name="requires_window" value="true"                        />
    <property name="window_partition" value="account_id"                 />
    <property name="window_order"     value="txn_timestamp"              />
    <property name="window_range"     value="-${VELOCITY_WINDOW_HOURS}h" />
    <port name="in"  type="input"  source="node_09.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Compute Composite Risk Score                        -->
  <!-- Combines base_rule_score + velocity_score + amount_score      -->
  <!-- ============================================================ -->

  <component id="node_11" name="ComputeRiskScore" type="Reformat">
    <property name="transform_file" value="compute_risk_score.xfr"  />
    <property name="schema"         value="txn_scored.dml"           />
    <port name="in"  type="input"  source="node_10.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- FAN-OUT NODE: node_11 feeds 3 downstream paths               -->
  <!-- Path A: HIGH RISK  → flagged output + blocked accounts agg   -->
  <!-- Path B: LOW RISK   → clean output                            -->
  <!-- Path C: ALL scored → regulatory aggregate                    -->
  <!-- ============================================================ -->

  <!-- ============================================================ -->
  <!-- FILTER: High-Risk Transactions  (score >= 75)                 -->
  <!-- ============================================================ -->

  <component id="node_12" name="FilterHighRisk" type="Filter">
    <property name="condition"      value="risk_score >= ${HIGH_RISK_SCORE}" />
    <property name="transform_file" value="filter_high_risk.xfr"             />
    <port name="in"  type="input"  source="node_11.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- FILTER: Clean (Low-Risk) Transactions  (score < 75)           -->
  <!-- ============================================================ -->

  <component id="node_13" name="FilterClean" type="Filter">
    <property name="condition"      value="risk_score < ${HIGH_RISK_SCORE}" />
    <property name="transform_file" value="filter_clean.xfr"                />
    <port name="in"  type="input"  source="node_11.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Enrich Flagged Transactions with Alert Metadata     -->
  <!-- Add alert_code, alert_reason, review_priority               -->
  <!-- ============================================================ -->

  <component id="node_14" name="EnrichFlaggedAlerts" type="Reformat">
    <property name="transform_file" value="enrich_flagged_alerts.xfr" />
    <property name="schema"         value="txn_flagged.dml"            />
    <port name="in"  type="input"  source="node_12.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- AGGREGATE: Blocked Accounts                                   -->
  <!-- Group flagged txns by account_id; flag account if             -->
  <!-- high-risk txn count > 3 in window                            -->
  <!-- ============================================================ -->

  <component id="node_15" name="AggregateBlockedAccounts" type="Aggregate">
    <property name="group_by"   value="account_id, account_holder_name, account_country" />
    <property name="aggregates" value="count(txn_id):high_risk_txn_count, max(risk_score):max_risk_score, sum(txn_amount):total_flagged_amount, max(txn_timestamp):last_flagged_at" />
    <property name="having"     value="count(txn_id) > 3"                                />
    <property name="schema"     value="blocked_account_summary.dml"                      />
    <port name="in"  type="input"  source="node_14.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- AGGREGATE: Regulatory Report                                   -->
  <!-- Monthly summary by country + txn_type for all scored txns    -->
  <!-- ============================================================ -->

  <component id="node_16" name="AggregateRegulatoryReport" type="Aggregate">
    <property name="group_by"   value="txn_month, account_country, txn_type"             />
    <property name="aggregates" value="count(txn_id):total_txn_count, sum(txn_amount):total_txn_volume, sum(if(risk_score >= 75, 1, 0)):flagged_count, avg(risk_score):avg_risk_score, max(txn_amount):max_single_txn" />
    <property name="schema"     value="regulatory_report.dml"                             />
    <port name="in"  type="input"  source="node_11.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- REFORMAT: Apply Report Date & Submission Metadata             -->
  <!-- Stamp the regulatory report with report_date + institution   -->
  <!-- ============================================================ -->

  <component id="node_17" name="StampRegulatoryReport" type="Reformat">
    <property name="transform_file" value="stamp_regulatory_report.xfr" />
    <property name="schema"         value="regulatory_report.dml"        />
    <port name="in"  type="input"  source="node_16.out" />
    <port name="out" type="output" />
  </component>

  <!-- ============================================================ -->
  <!-- OUTPUT COMPONENTS  (4 sinks)                                  -->
  <!-- ============================================================ -->

  <component id="node_18" name="FlaggedOutput" type="OutputFile">
    <property name="filename"    value="${OUTPUT_FLAGGED}" />
    <property name="file_format" value="parquet"           />
    <property name="mode"        value="overwrite"         />
    <property name="partition_by" value="txn_month"        />
    <port name="in" type="input" source="node_14.out" />
  </component>

  <component id="node_19" name="CleanOutput" type="OutputFile">
    <property name="filename"    value="${OUTPUT_CLEAN}"   />
    <property name="file_format" value="parquet"           />
    <property name="mode"        value="overwrite"         />
    <property name="partition_by" value="txn_month"        />
    <port name="in" type="input" source="node_13.out" />
  </component>

  <component id="node_20" name="RegulatoryOutput" type="OutputFile">
    <property name="filename"    value="${OUTPUT_REGULATORY}" />
    <property name="file_format" value="parquet"              />
    <property name="mode"        value="overwrite"            />
    <port name="in" type="input" source="node_17.out" />
  </component>

  <component id="node_21" name="BlockedAccountsOutput" type="OutputFile">
    <property name="filename"    value="${OUTPUT_BLOCKED}" />
    <property name="file_format" value="parquet"           />
    <property name="mode"        value="append"            />
    <port name="in" type="input" source="node_15.out" />
  </component>

  <!-- ============================================================ -->
  <!-- CONNECTIONS                                                   -->
  <!-- ============================================================ -->

  <connections>
    <!-- Input normalization -->
    <edge from="node_01" to="node_04" />   <!-- TransactionInput → NormalizeTransaction     -->
    <edge from="node_02" to="node_05" />   <!-- AccountInput → NormalizeAccount              -->
    <edge from="node_05" to="node_06" />   <!-- NormalizeAccount → FilterActiveAccounts      -->

    <!-- Pre-join filters -->
    <edge from="node_04" to="node_07" />   <!-- NormalizeTransaction → FilterValidTxns       -->

    <!-- Sequential joins -->
    <edge from="node_07" to="node_08" />   <!-- FilterValidTxns → JoinTxnAccount (left)      -->
    <edge from="node_06" to="node_08" />   <!-- FilterActiveAccounts → JoinTxnAccount (right) -->
    <edge from="node_08" to="node_09" />   <!-- JoinTxnAccount → JoinRiskRules (left)         -->
    <edge from="node_03" to="node_09" />   <!-- RiskRulesInput → JoinRiskRules (right)        -->

    <!-- Scoring chain -->
    <edge from="node_09" to="node_10" />   <!-- JoinRiskRules → ComputeVelocity              -->
    <edge from="node_10" to="node_11" />   <!-- ComputeVelocity → ComputeRiskScore           -->

    <!-- Fan-out from node_11 (out-degree = 3) -->
    <edge from="node_11" to="node_12" />   <!-- ComputeRiskScore → FilterHighRisk            -->
    <edge from="node_11" to="node_13" />   <!-- ComputeRiskScore → FilterClean               -->
    <edge from="node_11" to="node_16" />   <!-- ComputeRiskScore → AggregateRegulatoryReport -->

    <!-- High-risk path -->
    <edge from="node_12" to="node_14" />   <!-- FilterHighRisk → EnrichFlaggedAlerts          -->
    <edge from="node_14" to="node_15" />   <!-- EnrichFlaggedAlerts → AggregateBlockedAccts  -->
    <edge from="node_14" to="node_18" />   <!-- EnrichFlaggedAlerts → FlaggedOutput (fan-out) -->

    <!-- Clean path -->
    <edge from="node_13" to="node_19" />   <!-- FilterClean → CleanOutput                    -->

    <!-- Regulatory path -->
    <edge from="node_16" to="node_17" />   <!-- AggregateRegulatoryReport → StampReport      -->
    <edge from="node_17" to="node_20" />   <!-- StampReport → RegulatoryOutput               -->

    <!-- Blocked accounts output -->
    <edge from="node_15" to="node_21" />   <!-- AggBlockedAccts → BlockedAccountsOutput      -->
  </connections>

</graph>
