# Row-Level Security (RLS) Strategy - OEMMatInsightBI

**Status:** Design Complete
**Last Updated:** 2025-11-03
**Owner:** Claude Code

## Executive Summary

This document defines the Row-Level Security (RLS) implementation strategy for the OEMMatInsightBI semantic model. Currently, the model has **no RLS implementation** - all users see all data. This design creates a comprehensive security framework that restricts data access based on user roles, demonstrating enterprise-grade security patterns suitable for a portfolio project.

**Key Decisions:**
- ✅ **Role-Based Access Control (RBAC):** 6 roles covering realistic business scenarios
- ✅ **DAX Security Filters:** Dimension-level filters that automatically cascade to facts
- ✅ **Dynamic Security:** User-based filtering using `USERPRINCIPALNAME()` and security table
- ✅ **Multi-Role Support:** Users can have multiple roles with OR logic
- ✅ **Test Strategy:** Comprehensive validation scenarios with "View as Role" feature

**Expected Benefits:**
- **Data Governance:** Restrict sensitive procurement and ESG data by geography/category
- **Compliance:** Meet data privacy requirements for multinational operations
- **Portfolio Value:** Showcase enterprise security best practices
- **Flexibility:** Support organizational hierarchy with inherited permissions

---

## 1. Current State Analysis

### Semantic Model Structure

**Tables:**
- `fact_procurement` - Procurement transactions
- `fact_epi_score` - Environmental scores
- `fact_supply_share` - Supply chain data
- `gold_dim_country` - Country dimension (with **region** column)
- `gold_dim_material` - Material dimension (with **commodity_group** column)
- `gold_dim_date` - Date dimension
- `gold_dim_indicator` - ESG indicators
- `gold_dim_stage` - Supply chain stages

**Natural Segmentation Points:**
- **Geography:** `gold_dim_country[region]` - Americas, Europe, Asia, Asia-Pacific, Africa
- **Material Category:** `gold_dim_material[commodity_group]` - Battery metals, Base metals, Rare earths, etc.
- **Time:** `gold_dim_date` - Could restrict to recent years only
- **Indicator Type:** `gold_dim_indicator[indicator_source]` - EPI vs WGI

### Current Security Posture

**What Exists:**
- ✅ Fabric workspace permissions (Workspace Viewer, Contributor, Admin)
- ✅ Power BI app-level permissions (Read-only access)
- ❌ No RLS roles defined
- ❌ No row-level data filtering
- ❌ All authenticated users see all data

**Security Gap:**
Without RLS, a user with report access can see:
- All procurement data globally (including sensitive spend amounts)
- All supplier relationships (competitive intelligence risk)
- All ESG scores for all countries (potential misuse)

---

## 2. Role Definitions

### Role Hierarchy

```
Global Executive (Admin)
  ├─ Regional Procurement Director - Americas
  │   ├─ Procurement Manager - Americas
  │   └─ Sustainability Analyst - Americas
  ├─ Regional Procurement Director - Europe
  │   ├─ Procurement Manager - Europe
  │   └─ Sustainability Analyst - Europe
  ├─ Regional Procurement Director - Asia-Pacific
  │   ├─ Procurement Manager - Asia-Pacific
  │   └─ Sustainability Analyst - Asia-Pacific
  └─ Material Category Managers
      ├─ Category Manager - Battery Metals
      ├─ Category Manager - Base Metals
      └─ Category Manager - Rare Earths
```

### Role Specifications

#### Role 1: Global Executive
**Business Justification:** C-suite executives need full visibility into global procurement and ESG performance.

**Access Level:**
- ✅ All regions
- ✅ All materials
- ✅ All time periods
- ✅ All ESG indicators

**DAX Filter:**
```dax
// No filter = full access
```

**Test User:** `exec@swiftbiketech.com`

---

#### Role 2: Regional Procurement Manager - Americas
**Business Justification:** Regional managers responsible for procurement strategy in Americas need visibility into their region's spend, suppliers, and ESG performance.

**Access Level:**
- ✅ Region: Americas (North America, South America, Caribbean)
- ✅ All materials sourced from Americas suppliers
- ✅ All time periods
- ✅ All ESG indicators for Americas countries

**DAX Filter:**
```dax
// Apply to gold_dim_country table
[region] = "Americas"
```

**Cascading Effect:**
- `fact_procurement`: Filters to suppliers with HQ in Americas
- `fact_epi_score`: Filters to Americas countries only
- `fact_supply_share`: Filters to Americas supply chains

**Test User:** `manager.americas@swiftbiketech.com`

---

#### Role 3: Regional Procurement Manager - Europe
**Business Justification:** European managers handle EU regulations, GDPR compliance, and regional supply chain optimization.

**Access Level:**
- ✅ Region: Europe
- ✅ All materials sourced from European suppliers
- ✅ All time periods
- ✅ All ESG indicators for European countries

**DAX Filter:**
```dax
[region] = "Europe"
```

**Test User:** `manager.europe@swiftbiketech.com`

---

#### Role 4: Regional Procurement Manager - Asia-Pacific
**Business Justification:** APAC managers focus on Asian and Oceania suppliers, critical for high-tech materials.

**Access Level:**
- ✅ Region: Asia, Asia-Pacific, Oceania
- ✅ All materials sourced from APAC suppliers
- ✅ All time periods
- ✅ All ESG indicators for APAC countries

**DAX Filter:**
```dax
// APAC includes multiple region values
[region] IN {"Asia", "Asia-Pacific", "Oceania"}
```

**Test User:** `manager.apac@swiftbiketech.com`

---

#### Role 5: Category Manager - Battery Metals
**Business Justification:** Material category managers focus on specific commodity groups (Lithium, Cobalt, etc.) regardless of geography.

**Access Level:**
- ✅ All regions
- ✅ Materials: Battery metals commodity group only
- ✅ All time periods
- ✅ ESG scores for countries supplying battery metals

**DAX Filter:**
```dax
// Apply to gold_dim_material table
[commodity_group] = "Battery metals"
```

**Cascading Effect:**
- `fact_procurement`: Filters to battery metal transactions only
- `fact_supply_share`: Filters to battery metal supply chains
- `fact_epi_score`: No direct filter (shows all countries, but procurement context limits)

**Test User:** `category.batterymetals@swiftbiketech.com`

---

#### Role 6: Category Manager - Base Metals
**Business Justification:** Similar to battery metals, but focused on copper, aluminum, steel, etc.

**Access Level:**
- ✅ All regions
- ✅ Materials: Base metals commodity group only
- ✅ All time periods

**DAX Filter:**
```dax
[commodity_group] = "Base metals"
```

**Test User:** `category.basemetals@swiftbiketech.com`

---

### Role Comparison Matrix

| Role | Geography | Materials | Time | ESG Data | Use Case |
|------|-----------|-----------|------|----------|----------|
| **Global Executive** | All | All | All | All | Strategic oversight |
| **Regional Manager - Americas** | Americas only | All | All | Americas only | Regional strategy |
| **Regional Manager - Europe** | Europe only | All | All | Europe only | EU compliance |
| **Regional Manager - APAC** | APAC only | All | All | APAC only | Asia sourcing |
| **Category Manager - Battery Metals** | All | Battery metals only | All | Contextual | Commodity strategy |
| **Category Manager - Base Metals** | All | Base metals only | All | Contextual | Commodity strategy |

---

## 3. DAX Security Filter Implementation

### 3.1 Static Role Filters

**Filter Table:** `gold_dim_country`

**Role: Regional Manager - Americas**
```dax
// In Power BI: Modeling > Manage Roles > Create Role > Add DAX Filter
// Table: gold_dim_country
[region] = "Americas"
```

**Role: Regional Manager - Europe**
```dax
[region] = "Europe"
```

**Role: Regional Manager - APAC**
```dax
// Multiple values using IN
[region] IN {"Asia", "Asia-Pacific", "Oceania"}
```

---

**Filter Table:** `gold_dim_material`

**Role: Category Manager - Battery Metals**
```dax
[commodity_group] = "Battery metals"
```

**Role: Category Manager - Base Metals**
```dax
[commodity_group] = "Base metals"
```

**Role: Category Manager - Rare Earths** (if added later)
```dax
[commodity_group] = "Rare earths"
```

---

### 3.2 Dynamic Security Filters

**Approach:** Use a security mapping table to assign users to regions/categories dynamically.

**Step 1: Create Security Table**

**Table:** `dim_security_users` (in warehouse or lakehouse)

```sql
CREATE TABLE dim_security_users (
    user_email VARCHAR(255) PRIMARY KEY,
    user_name VARCHAR(255),
    role_type VARCHAR(50),  -- 'Regional' or 'Category'
    access_value VARCHAR(100)  -- Region name or Commodity group
);

-- Sample data
INSERT INTO dim_security_users VALUES
('exec@swiftbiketech.com', 'Jane Executive', 'Global', NULL),
('manager.americas@swiftbiketech.com', 'John Americas', 'Regional', 'Americas'),
('manager.europe@swiftbiketech.com', 'Marie Europe', 'Regional', 'Europe'),
('manager.apac@swiftbiketech.com', 'Li APAC', 'Regional', 'Asia-Pacific'),
('category.batterymetals@swiftbiketech.com', 'Sarah Battery', 'Category', 'Battery metals'),
('category.basemetals@swiftbiketech.com', 'Mike Base', 'Category', 'Base metals');
```

**Step 2: Load Security Table to Semantic Model**
- Add `dim_security_users` to semantic model
- Mark as hidden (users don't need to see it)
- No relationships to other tables

**Step 3: Dynamic DAX Filters**

**Role: Dynamic Regional Manager**
```dax
// Apply to gold_dim_country
VAR CurrentUser = USERPRINCIPALNAME()
VAR UserRegion =
    LOOKUPVALUE(
        dim_security_users[access_value],
        dim_security_users[user_email], CurrentUser,
        dim_security_users[role_type], "Regional"
    )
RETURN
    IF(
        ISBLANK(UserRegion),  // If user not found, deny all access
        FALSE(),
        [region] = UserRegion
    )
```

**Role: Dynamic Category Manager**
```dax
// Apply to gold_dim_material
VAR CurrentUser = USERPRINCIPALNAME()
VAR UserCategory =
    LOOKUPVALUE(
        dim_security_users[access_value],
        dim_security_users[user_email], CurrentUser,
        dim_security_users[role_type], "Category"
    )
RETURN
    IF(
        ISBLANK(UserCategory),
        FALSE(),
        [commodity_group] = UserCategory
    )
```

**Benefits of Dynamic Security:**
- ✅ No need to create new Power BI roles when users change
- ✅ Centralized security management (update database table)
- ✅ Easier auditing (security assignments in queryable table)
- ✅ Supports complex scenarios (multi-role, time-based access)

---

### 3.3 Multi-Role Support

**Scenario:** A user is both Regional Manager (Americas) AND Category Manager (Battery Metals).

**Challenge:** Power BI applies roles with OR logic, so user gets union of both filters.

**Solution 1: Create Combined Roles**
```dax
// Role: Regional Manager Americas + Battery Metals Category
// Filter on gold_dim_country
[region] = "Americas"

// Filter on gold_dim_material
[commodity_group] = "Battery metals"

// Result: User sees Battery metals from Americas suppliers only (AND logic)
```

**Solution 2: Dynamic Multi-Role Logic**
```sql
-- Security table with multiple rows per user
INSERT INTO dim_security_users VALUES
('hybrid.user@swiftbiketech.com', 'Hybrid User', 'Regional', 'Americas'),
('hybrid.user@swiftbiketech.com', 'Hybrid User', 'Category', 'Battery metals');
```

```dax
// Dynamic filter with multi-role support
VAR CurrentUser = USERPRINCIPALNAME()
VAR UserRegions =
    CALCULATETABLE(
        VALUES(dim_security_users[access_value]),
        dim_security_users[user_email] = CurrentUser,
        dim_security_users[role_type] = "Regional"
    )
RETURN
    [region] IN UserRegions
```

---

## 4. Testing Strategy

### 4.1 "View as Role" Testing (Power BI Desktop)

**Steps:**
1. Open semantic model in Power BI Desktop
2. Navigate to: **Modeling > Security > View as Roles**
3. Select role to test (e.g., "Regional Manager - Americas")
4. Optional: Enter test user email for dynamic security
5. Report now shows data as that role sees it

**Test Scenarios:**

**Test 1: Regional Manager - Americas**
```
Expected:
- Country visuals show only Americas countries (USA, Canada, Mexico, Brazil, etc.)
- Total Spend EUR is subset of global spend
- Materials shown: All materials, but only from Americas suppliers
- EPI scores: Only Americas countries visible

Validation:
- Check country list in slicer: Should NOT show China, Germany, etc.
- Check spend total: Should be ~30% of global total (if Americas = 30% of spend)
```

**Test 2: Category Manager - Battery Metals**
```
Expected:
- Material visuals show only: Lithium, Cobalt, Nickel, Manganese, Graphite
- Total Spend EUR is subset (battery metals only)
- Countries shown: All countries that supply battery metals
- EPI scores: All countries visible

Validation:
- Check material list: Should NOT show Copper, Aluminum, etc.
- Check spend total: Should be ~40% of global total (if battery = 40%)
```

**Test 3: Global Executive**
```
Expected:
- All data visible (no filters)
- Country count: All countries
- Material count: All materials
- Total spend: 100% of global spend

Validation:
- Compare totals to "View as Role = None" (admin view)
- Should be identical
```

### 4.2 Integration Testing with Visuals

**Visual 1: Matrix - Region x Material**
```
Rows: gold_dim_country[region]
Columns: gold_dim_material[commodity_group]
Values: Total Spend EUR

Test as Regional Manager - Americas:
- Rows should show ONLY "Americas"
- Columns should show all commodity groups
- Totals should match Americas-only total
```

**Visual 2: Map - Spend by Country**
```
Location: gold_dim_country[country_name]
Size: Total Spend EUR

Test as Regional Manager - Europe:
- Map should show ONLY European countries
- No markers in Americas, Asia, etc.
- Zoom to Europe should show all suppliers
```

**Visual 3: Bar Chart - Top 10 Materials**
```
Axis: gold_dim_material[material_name]
Values: Total Spend EUR

Test as Category Manager - Battery Metals:
- Chart should show max 5-7 materials (battery metals only)
- Should NOT show Copper, Aluminum, Steel, etc.
- Order should be by spend within battery metals
```

### 4.3 Cross-Filter Testing

**Scenario:** User with Americas role applies slicer filter for "China"

**Expected Behavior:**
1. RLS filter: `region = "Americas"`
2. User filter: `country_name = "China"`
3. Result: Empty report (no data matches both filters)
4. Visuals show blank or "No data available"

**Validation:**
- Ensure no data leakage (user can't see China data by manipulating slicers)
- Confirm error messages are user-friendly
- Verify report doesn't crash with empty context

---

## 5. Security Audit & Logging

### 5.1 Audit Table Design

**Table:** `gold_security_audit_log` (optional)

```sql
CREATE TABLE gold_security_audit_log (
    audit_id BIGINT IDENTITY PRIMARY KEY,
    event_timestamp DATETIME2 DEFAULT GETDATE(),
    user_email VARCHAR(255),
    user_role VARCHAR(100),
    report_name VARCHAR(255),
    page_name VARCHAR(255),
    filter_context TEXT,  -- JSON of active filters
    rows_returned BIGINT,
    execution_time_ms INT
);
```

**Audit Trigger:**
- Log every report refresh/page view
- Capture user, role, filters applied
- Track how many rows returned (detect unusual access patterns)

**Example Audit Queries:**
```sql
-- Users accessing the most data
SELECT
    user_email,
    user_role,
    COUNT(*) as access_count,
    AVG(rows_returned) as avg_rows,
    MAX(rows_returned) as max_rows
FROM gold_security_audit_log
WHERE event_timestamp >= DATEADD(day, -30, GETDATE())
GROUP BY user_email, user_role
ORDER BY avg_rows DESC;

-- Detect potential security violations (user seeing more data than expected)
SELECT *
FROM gold_security_audit_log
WHERE user_role = 'Regional Manager - Americas'
  AND rows_returned > 10000  -- Threshold for Americas data
ORDER BY event_timestamp DESC;
```

### 5.2 RLS Compliance Checklist

**Before deploying RLS:**
- [ ] All sensitive tables have RLS filters applied
- [ ] Test users created for each role
- [ ] "View as Role" tested for each role
- [ ] Cross-filter testing completed (no data leakage)
- [ ] Documentation created for role assignment
- [ ] Security table (dim_security_users) populated
- [ ] Audit logging configured (if applicable)
- [ ] User training scheduled

---

## 6. Best Practices & Performance

### 6.1 RLS Performance Optimization

**Problem:** RLS filters add computation overhead (especially with `USERPRINCIPALNAME()` lookups).

**Best Practices:**

**1. Filter on Dimension Tables (Not Facts)**
```dax
// Good: Filter on dimension
gold_dim_country[region] = "Americas"

// Bad: Filter on fact (slow)
CALCULATE(
    TRUE(),
    FILTER(
        ALL(fact_procurement),
        RELATED(gold_dim_country[region]) = "Americas"
    )
)
```
**Reason:** Dimension filters cascade to facts via relationships. Filtering facts directly creates row context iteration (slow).

---

**2. Avoid Complex DAX in RLS Filters**
```dax
// Bad: Complex calculation in RLS filter
VAR CurrentUser = USERPRINCIPALNAME()
VAR UserSpendThreshold = LOOKUPVALUE(dim_security_users[spend_limit], dim_security_users[user_email], CurrentUser)
RETURN
    CALCULATE([Total Spend EUR]) <= UserSpendThreshold

// Problem: Recalculates spend threshold for every row evaluation
```

**Good Alternative:** Pre-calculate and store in security table as categorical values.

---

**3. Use Static Roles When Possible**
```dax
// Faster: Static role
[region] = "Americas"

// Slower: Dynamic role with lookup
VAR CurrentUser = USERPRINCIPALNAME()
VAR UserRegion = LOOKUPVALUE(...)
RETURN [region] = UserRegion
```

**Recommendation:** Use static roles for well-defined access patterns. Use dynamic only when security assignments change frequently.

---

### 6.2 Security Table Design Best Practices

**Minimize Lookups:**
```sql
-- Good: Denormalized (one row per user, all access in one record)
CREATE TABLE dim_security_users (
    user_email VARCHAR(255) PRIMARY KEY,
    allowed_regions VARCHAR(1000),  -- 'Americas,Europe'
    allowed_categories VARCHAR(1000)  -- 'Battery metals,Base metals'
);

-- DAX Filter
VAR CurrentUser = USERPRINCIPALNAME()
VAR AllowedRegions = LOOKUPVALUE(dim_security_users[allowed_regions], dim_security_users[user_email], CurrentUser)
RETURN
    [region] IN SPLIT(AllowedRegions, ",")
```

**Benefits:**
- Single lookup per user (not one per role type)
- Supports multi-value access easily
- Better performance in large user bases

---

### 6.3 Testing for Performance Impact

**Benchmark Tests:**

**Test 1: Report Load Time (No RLS vs With RLS)**
```
Scenario: Load main dashboard
Metric: Time to first visual render

Expected Results:
- No RLS: 1.2 seconds
- With Static RLS: 1.4 seconds (+17%)
- With Dynamic RLS: 1.8 seconds (+50%)

Acceptable Threshold: <2 seconds for all scenarios
```

**Test 2: Matrix with 1000s of Rows**
```
Scenario: Material x Country matrix (100 materials x 50 countries)
Metric: Render time

Expected Results:
- No RLS: 3.5 seconds
- With RLS (dimension filter): 3.8 seconds (+9%)
- With RLS (fact filter - bad practice): 12 seconds (+243%)

Lesson: Always filter dimensions, not facts
```

---

## 7. Advanced Scenarios

### 7.1 Time-Based Access (Expiring Permissions)

**Use Case:** Contractor has access to data for 3 months only.

**Security Table:**
```sql
ALTER TABLE dim_security_users
ADD access_start_date DATE,
    access_end_date DATE;

INSERT INTO dim_security_users VALUES
('contractor@external.com', 'Temp Contractor', 'Regional', 'Americas', '2024-01-01', '2024-03-31');
```

**DAX Filter:**
```dax
VAR CurrentUser = USERPRINCIPALNAME()
VAR AccessStart = LOOKUPVALUE(dim_security_users[access_start_date], dim_security_users[user_email], CurrentUser)
VAR AccessEnd = LOOKUPVALUE(dim_security_users[access_end_date], dim_security_users[user_email], CurrentUser)
VAR Today = TODAY()
RETURN
    Today >= AccessStart && Today <= AccessEnd && [region] = "Americas"
```

**Benefit:** Automatically revoke access after end date (no manual role removal needed).

---

### 7.2 Hierarchical Security (Manager Sees Team Data)

**Use Case:** Regional Director sees all data for their direct reports.

**Security Table:**
```sql
CREATE TABLE dim_security_hierarchy (
    manager_email VARCHAR(255),
    report_email VARCHAR(255)
);

-- Example: Director sees their team's regions
INSERT INTO dim_security_hierarchy VALUES
('director.americas@swiftbiketech.com', 'manager.northamerica@swiftbiketech.com'),
('director.americas@swiftbiketech.com', 'manager.southamerica@swiftbiketech.com');
```

**DAX Filter:**
```dax
// Allow user to see their own data + their reports' data
VAR CurrentUser = USERPRINCIPALNAME()
VAR UserRegion = LOOKUPVALUE(dim_security_users[access_value], dim_security_users[user_email], CurrentUser)
VAR TeamRegions =
    CALCULATETABLE(
        VALUES(dim_security_users[access_value]),
        FILTER(
            dim_security_hierarchy,
            dim_security_hierarchy[manager_email] = CurrentUser
        )
    )
VAR AllAllowedRegions = UNION(VALUES(UserRegion), TeamRegions)
RETURN
    [region] IN AllAllowedRegions
```

**Benefit:** Managers automatically inherit team permissions without explicit assignment.

---

### 7.3 Data Masking (Redact Sensitive Columns)

**Use Case:** Some users can see spend trends but not exact amounts.

**Approach:** Create calculated column in fact table with RLS-aware masking.

**Calculated Column in fact_procurement:**
```dax
[spend_eur_masked] =
VAR CurrentUser = USERPRINCIPALNAME()
VAR UserRole = LOOKUPVALUE(dim_security_users[role_type], dim_security_users[user_email], CurrentUser)
VAR MaskData = (UserRole = "Analyst")  // Analysts see masked data
RETURN
    IF(
        MaskData,
        ROUND([spend_eur], -3),  // Round to nearest 1000 (e.g., 45,231 -> 45,000)
        [spend_eur]  // Managers see exact amounts
    )
```

**Usage:** Replace `Total Spend EUR = SUM(fact_procurement[spend_eur])` with `SUM([spend_eur_masked])` in measures.

---

## 8. Documentation & Training

### 8.1 User-Facing Documentation

**Title:** "OEMMatInsightBI Data Access Guide"

**Sections:**
1. **Your Role & Access Level**
   - Explanation of role (Regional Manager, Category Manager, etc.)
   - What data you can see
   - What data you cannot see

2. **Understanding Filtered Reports**
   - Why some visuals are blank (filter context)
   - How to interpret "No data" messages
   - When to contact support

3. **Security Best Practices**
   - Do not share credentials
   - Log out when finished
   - Report suspicious access patterns

### 8.2 Administrator Guide

**Title:** "RLS Administration & Role Assignment"

**Sections:**
1. **Adding New Users**
   ```sql
   -- Template for adding new regional manager
   INSERT INTO dim_security_users
   VALUES ('new.user@company.com', 'New User Name', 'Regional', 'Europe');
   ```

2. **Modifying Existing Access**
   ```sql
   -- Update user region
   UPDATE dim_security_users
   SET access_value = 'Asia-Pacific'
   WHERE user_email = 'user@company.com';
   ```

3. **Testing New Roles**
   - Use "View as Role" feature
   - Create test reports
   - Validate data volumes

4. **Troubleshooting Access Issues**
   - User reports "no data": Check role assignment
   - User sees unexpected data: Check for multiple roles
   - Performance issues: Review DAX filter complexity

---

## 9. Implementation Checklist

### Phase 1: Design & Planning (0.5 days)
- [x] Define business roles (6 roles documented)
- [x] Identify dimension filter points (region, commodity_group)
- [x] Design security table schema (dim_security_users)
- [x] Document DAX filter logic

### Phase 2: Security Table Creation (0.5 days)
- [ ] Create `dim_security_users` table in warehouse
- [ ] Populate with test users (6+ users)
- [ ] Load table into semantic model
- [ ] Mark table as hidden
- [ ] Verify table refresh in Power BI

### Phase 3: Static Role Implementation (1 day)
- [ ] Create 6 static roles in semantic model:
  - [ ] Global Executive (no filter)
  - [ ] Regional Manager - Americas
  - [ ] Regional Manager - Europe
  - [ ] Regional Manager - APAC
  - [ ] Category Manager - Battery Metals
  - [ ] Category Manager - Base Metals
- [ ] Apply DAX filters to dimension tables
- [ ] Test each role with "View as Role"

### Phase 4: Dynamic Role Implementation (0.5 days - Optional)
- [ ] Create dynamic role: "Dynamic Regional Manager"
- [ ] Create dynamic role: "Dynamic Category Manager"
- [ ] Implement `USERPRINCIPALNAME()` lookup logic
- [ ] Test with test user emails
- [ ] Validate multi-role scenarios

### Phase 5: Validation & Testing (1 day)
- [ ] **Test Scenario 1:** Regional Manager sees only their region
- [ ] **Test Scenario 2:** Category Manager sees only their materials
- [ ] **Test Scenario 3:** Global Executive sees all data
- [ ] **Test Scenario 4:** Cross-filter testing (no data leakage)
- [ ] **Test Scenario 5:** Multi-role user (correct AND/OR logic)
- [ ] Performance testing (benchmark report load times)
- [ ] Take screenshots for portfolio documentation

### Phase 6: Documentation (0.5 days)
- [ ] Create user-facing access guide
- [ ] Create administrator role assignment guide
- [ ] Document test results
- [ ] Create RLS troubleshooting runbook

---

## 10. Portfolio Demonstration

### Screenshots to Capture

**Screenshot 1: Role Management UI**
- Power BI Desktop: Modeling > Manage Roles
- Show all 6 roles with DAX filters visible

**Screenshot 2: Regional Manager View**
- Dashboard filtered to Americas only
- Highlight: Country slicer shows only Americas countries
- Highlight: Total spend is subset of global

**Screenshot 3: Category Manager View**
- Dashboard filtered to Battery metals only
- Highlight: Material list shows only Lithium, Cobalt, etc.

**Screenshot 4: Security Table**
- Excel or SQL view of `dim_security_users`
- Show user-to-role mappings

### Talking Points for Portfolio

**Security Design:**
"Implemented enterprise-grade Row-Level Security with 6 role-based access patterns covering regional and category-based segmentation. Used DAX security filters on dimension tables to efficiently cascade restrictions to fact tables via star schema relationships."

**Dynamic Security:**
"Designed dynamic security framework using `USERPRINCIPALNAME()` and security mapping table, enabling centralized role management without creating new Power BI roles for every user. This pattern supports organizational hierarchy and time-based access expiration."

**Testing & Validation:**
"Comprehensive testing strategy using Power BI's 'View as Role' feature, validating 5+ scenarios including multi-role users and cross-filter testing to ensure no data leakage. Performance benchmarked with <2 second report load times across all roles."

---

## 11. Future Enhancements

### Dynamic Data Masking
- Redact exact spend amounts for certain roles
- Show aggregates only (no drill-down to transaction level)

### Object-Level Security (OLS)
- Hide entire columns from certain roles
- Example: Hide `unitprice_eur` from Sustainability Analysts

### Attribute-Based Access Control (ABAC)
- Access based on user attributes (department, job level, clearance)
- More flexible than role-based (combine multiple attributes)

### Integration with Azure AD Groups
- Sync roles with Azure AD security groups
- Automatic role assignment when user added to group

---

## 12. References

### Microsoft Documentation
- **RLS in Power BI:** https://learn.microsoft.com/power-bi/enterprise/service-admin-rls
- **Dynamic RLS:** https://learn.microsoft.com/power-bi/guidance/rls-guidance#dynamic-rls
- **USERPRINCIPALNAME():** https://dax.guide/userprincipalname/

### Best Practices
- **SQLBI RLS Patterns:** https://www.sqlbi.com/articles/row-level-security-in-power-bi/
- **Dynamic Security:** https://www.sqlbi.com/articles/implementing-dynamic-row-level-security-in-power-bi/

---

**Document Status:** Design complete and ready for implementation
**Implementation Effort:** 4 days (setup to final testing)
**Next Task:** Task 07 (Data Quality Framework Design)

---

## Summary: 6 Roles + Dynamic Security

**Static Roles (6):**
1. Global Executive - Full access
2. Regional Manager - Americas - Region filter
3. Regional Manager - Europe - Region filter
4. Regional Manager - APAC - Region filter
5. Category Manager - Battery Metals - Material filter
6. Category Manager - Base Metals - Material filter

**Dynamic Roles (2 optional):**
1. Dynamic Regional Manager - Uses security table
2. Dynamic Category Manager - Uses security table

**Security Patterns Demonstrated:**
✅ Static DAX filters on dimensions
✅ Dynamic USERPRINCIPALNAME() lookups
✅ Multi-role support with AND/OR logic
✅ Time-based access (expiring permissions)
✅ Hierarchical security (managers see team data)
✅ Performance optimization (dimension vs fact filtering)
✅ Comprehensive testing strategy
