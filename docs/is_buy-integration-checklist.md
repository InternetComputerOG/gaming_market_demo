# is_buy Field Integration Checklist

## Overview

This document provides a comprehensive checklist for adding the missing `is_buy` boolean field to the `orders` table and integrating it across all affected components in the Gaming Market Demo application.

**Root Cause:** The engine interface requires `is_buy` field for order processing, but the `orders` table schema is missing this field, causing order submission failures and incorrect batch processing.

**Solution:** Add `is_buy` field to database schema and integrate across all affected files with minimal changes following the Implementation Plan requirements.

---

## Database Schema Changes

### 1. Update `app/db/schema.sql`
- [x] Add `is_buy BOOLEAN NOT NULL` column to `orders` table
- [x] Position after `type` field for logical grouping
- [x] Ensure field is NOT NULL to prevent ambiguity
- [x] Add index on `is_buy` for query performance if needed

**Expected Change:**
```sql
-- orders table: Submitted orders
CREATE TABLE orders (
    order_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    outcome_i INTEGER NOT NULL,
    yes_no yes_no_enum NOT NULL,
    type order_type_enum NOT NULL,
    is_buy BOOLEAN NOT NULL,  -- NEW FIELD: Buy (true) vs Sell (false) direction
    size NUMERIC(18,6) NOT NULL,
    -- ... rest of fields unchanged
);
```

### 2. Create Migration Script
- [x] Create `app/db/migrations/004_add_is_buy_to_orders.sql`
- [x] Add `is_buy` column with default value for existing orders
- [x] Handle any existing test data appropriately

**Expected Migration:**
```sql
-- Migration: Add is_buy field to orders table
ALTER TABLE orders ADD COLUMN is_buy BOOLEAN;

-- Set default value for any existing orders (assume BUY for safety)
UPDATE orders SET is_buy = true WHERE is_buy IS NULL;

-- Make field NOT NULL after setting defaults
ALTER TABLE orders ALTER COLUMN is_buy SET NOT NULL;

-- Optional: Add index for query performance
CREATE INDEX idx_orders_is_buy ON orders(is_buy);
```

---

## Code Integration Changes

### 3. Update Order Creation - `app/services/orders.py`
- [x] **REMOVE** the problematic `'is_buy': is_buy` line from order dictionary
- [x] **ADD** `is_buy` parameter to the order dictionary for database storage
- [x] Ensure `is_buy` is passed from UI and stored correctly
- [x] Update function signature if needed to accept `is_buy` parameter

**Current Issue (Line ~133):**
```python
order: Order = {
    'user_id': user_id,
    'outcome_i': outcome_i,
    'yes_no': yes_no,
    'type': order_type,
    'is_buy': is_buy,  # ❌ CAUSES DB ERROR - field doesn't exist
    # ... rest of fields
}
```

**Expected Fix:**
```python
order: Order = {
    'user_id': user_id,
    'outcome_i': outcome_i,
    'yes_no': yes_no,
    'type': order_type,
    'is_buy': is_buy,  # ✅ NOW WORKS - field exists in DB
    # ... rest of fields
}
```

### 4. Update Batch Runner - `app/runner/batch_runner.py`
- [x] **REMOVE** the fallback `db_order.get('is_buy', True)` logic
- [x] **USE** the actual stored `is_buy` value from database
- [x] Remove the "default to True" workaround that was masking the issue

**Current Issue (Line ~101):**
```python
'is_buy': db_order.get('is_buy', True),  # ❌ Defaults to True, breaks sell orders
```

**Expected Fix:**
```python
'is_buy': db_order['is_buy'],  # ✅ Use actual stored value
```

### 5. Update Database Queries - `app/db/queries.py`
- [x] Verify `insert_order()` function handles `is_buy` field correctly
- [x] Verify `fetch_open_orders()` returns `is_buy` field
- [x] Add any missing field handling if needed
- [x] Ensure proper type conversion (boolean handling)

### 6. Update UI Integration - `app/streamlit_app.py`
- [x] Verify `is_buy = direction == 'Buy'` logic is correct
- [x] Ensure `is_buy` is passed to `submit_order()` function
- [x] Verify order data dictionary includes `is_buy` field
- [x] Test both Buy and Sell directions work correctly

**Current Implementation (Line ~199):**
```python
is_buy = direction == 'Buy'  # ✅ This logic is correct
```

**Order Data (Line ~323):**
```python
'is_buy': is_buy,  # ✅ This should work once DB field exists
```

---

## Testing & Validation

### 7. Database Testing
- [x] Run migration script on test database
- [x] Verify `orders` table has `is_buy` column
- [x] Test inserting orders with both `is_buy=true` and `is_buy=false`
- [x] Verify indexes are created correctly

### 8. Order Flow Testing
- [x] Test **BUY YES** orders (most common case)
- [x] Test **SELL YES** orders
- [x] Test **BUY NO** orders  
- [x] Test **SELL NO** orders
- [x] Verify batch runner processes all combinations correctly
- [x] Verify engine receives correct `is_buy` values

**Note:** Fixed critical AMM user ID bug - engine was using string 'AMM' instead of valid UUID for AMM trades, causing database foreign key constraint violations. Created special AMM user (UUID: 00000000-0000-0000-0000-000000000000) and updated engine/services code to use it.

### 9. End-to-End Integration Testing
- [ ] Submit market orders via UI for all 4 combinations
- [ ] Verify orders are stored with correct `is_buy` values
- [ ] Verify batch runner fetches and processes orders correctly
- [ ] Verify engine calculations use correct directionality
- [ ] Verify trades are generated and positions updated correctly

---

## Documentation Updates

### 10. Update Documentation
- [ ] Update Implementation Plan if needed (Section 5 - Data Model)
- [ ] Update any API documentation mentioning order fields
- [ ] Update README if database setup instructions change

---

## Rollback Plan

### 11. Rollback Strategy (if needed)
- [ ] Create rollback migration to remove `is_buy` column
- [ ] Revert code changes to use derivation logic
- [ ] Document rollback procedure

**Rollback Migration:**
```sql
-- Rollback: Remove is_buy field from orders table
ALTER TABLE orders DROP COLUMN is_buy;
DROP INDEX IF EXISTS idx_orders_is_buy;
```

---

## Success Criteria

### 12. Definition of Done
- [ ] ✅ Database schema includes `is_buy` field in `orders` table
- [ ] ✅ Order creation stores actual user direction (Buy/Sell)
- [ ] ✅ Batch runner uses stored `is_buy` values (no defaults)
- [ ] ✅ Engine receives correct directionality for all order types
- [ ] ✅ All 4 order combinations work: BUY/SELL × YES/NO
- [ ] ✅ Market orders process correctly and update positions
- [ ] ✅ No database errors during order submission
- [ ] ✅ Order processing completes end-to-end successfully

---

## Implementation Order

**Recommended sequence to minimize downtime:**

1. **Database First:** Update schema and run migration
2. **Code Second:** Update order creation and batch runner  
3. **Test Third:** Comprehensive testing of all combinations
4. **Deploy Fourth:** Deploy changes and monitor

This approach ensures the database is ready before code expects the field to exist.

---

## Notes

- **Minimal Scope:** This change only adds the missing field and integrates it. No additional features.
- **Engine Compatibility:** Maintains exact compatibility with existing engine interface.
- **User Intent Preservation:** Stores actual user buy/sell decisions rather than deriving them.
- **Audit Trail:** Provides clear record of user trading intentions.
- **Performance:** Minimal impact - single boolean field with optional index.

---

*This checklist ensures systematic integration of the `is_buy` field across all affected components while maintaining the scope and requirements of the Implementation Plan.*
