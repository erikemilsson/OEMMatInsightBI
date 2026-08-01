# Feedback Log

Items are captured via `/feedback` and triaged via `/feedback review`.

---

## FB-009: Remove leftover laptop firewall rule on the Azure SQL server

**Status:** new
**Captured:** 2026-08-01

During task-046 diagnostics (2026-07-31) a firewall rule `erik-laptop` = `37.247.31.201/32` was added to the `procurement-supplier` Azure SQL server so the laptop could reach the DB for credential reset/testing. That rule is still live. The pipeline no longer needs it — task-048 retired the bronze_azureSQLdb2table dataflow and the Azure SQL path now runs through the Fabric Connection `oem_azuresql_procurement` (executes in the Fabric runtime, not from the laptop). An allow-listed laptop IP on a production SQL server is a security loose end. Remove via Azure portal or `az sql server firewall-rule delete -g <rg> -s procurement-supplier -n erik-laptop`.

**Why it surfaced:** task-046 close-out review of leftover diagnostic state. The pipeline's SPN/Connection path makes the laptop rule obsolete.