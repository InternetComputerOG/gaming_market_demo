# Engine Order Rejection Handling - Demo Implementation Plan

## Overview
This document outlines the minimal, demo-focused implementation plan for handling engine order rejections in the Gaming Market Demo. The plan prioritizes essential functionality over best practices to meet the 8-hour demo deadline.

## Current State Analysis

### ✅ Already Working
- **Engine**: Generates `ORDER_REJECTED` events with detailed reasons
- **Batch Runner**: Processes `ORDER_REJECTED` events and updates order status to 'REJECTED'
- **Database**: Schema supports 'REJECTED' status in `order_status_enum`
- **Infrastructure**: All core rejection handling infrastructure is in place

### ❌ Critical Gaps
1. **Collateral Refunds**: Rejected limit orders don't refund committed collateral
2. **UI Visibility**: Users can't see rejected orders or reasons
3. **Admin Monitoring**: No rejection metrics for troubleshooting

## Minimal Implementation Plan

### Priority 1: Collateral Refund System (CRITICAL)
**Problem**: Users lose committed collateral when limit orders are rejected
**Solution**: Enhance batch runner to refund collateral for rejected orders

**Implementation**: 
- Modify `batch_runner.py` event processing to handle collateral refunds
- Add refund logic for `ORDER_REJECTED` events:
  - **Limit Buy**: Refund `size * limit_price` (keep gas fee)
  - **Limit Sell**: Refund `size tokens` (keep gas fee)
  - **Market Orders**: No refund needed (only gas fee deducted)

**Files to Modify**: 
- `app/runner/batch_runner.py` (lines 200-230)

### Priority 2: UI Rejected Orders Display (HIGH)
**Problem**: Users have no visibility into rejected orders
**Solution**: Add "Rejected Orders" tab to portfolio view

**Implementation**:
- Add third tab to portfolio section in `streamlit_app.py`
- Fetch rejected orders using existing `fetch_user_orders(user_id, 'REJECTED')`
- Display rejection reasons from event payloads
- Show refund status

**Files to Modify**:
- `app/streamlit_app.py` (portfolio section around line 996)

### Priority 3: Basic Admin Metrics (MEDIUM)
**Problem**: Admins can't monitor rejection rates
**Solution**: Add simple rejection count to admin dashboard

**Implementation**:
- Add rejection count query to admin dashboard
- Display total rejections and rejection rate
- Show breakdown by rejection reason

**Files to Modify**:
- `app/streamlit_admin.py` (admin monitoring section)

## Implementation Details

### 1. Batch Runner Collateral Refunds

```python
# In batch_runner.py, enhance ORDER_REJECTED event processing
if event['type'] == 'ORDER_REJECTED':
    # Get original order details for refund calculation
    order_details = fetch_order_details(order_id)
    if order_details:
        refund_collateral_for_rejected_order(order_details, payload.get('reason'))
```

### 2. UI Rejected Orders Tab

```python
# In streamlit_app.py, add third portfolio tab
pos_tab1, pos_tab2, pos_tab3 = st.tabs(["🏆 Filled Positions", "⏳ Open Orders", "❌ Rejected Orders"])

with pos_tab3:
    rejected_orders = fetch_user_orders(user_id, 'REJECTED')
    # Display rejected orders with reasons and refund status
```

### 3. Admin Rejection Metrics

```python
# In streamlit_admin.py, add rejection monitoring
rejection_count = count_orders_by_status('REJECTED')
total_orders = count_all_orders()
rejection_rate = rejection_count / total_orders if total_orders > 0 else 0
st.metric("Rejection Rate", f"{rejection_rate:.1%}")
```

## Database Schema Changes

### Minimal Schema Addition (Optional)
If time permits, add rejection reason storage:

```sql
-- Add rejection_reason column to orders table
ALTER TABLE orders ADD COLUMN rejection_reason TEXT;
```

**Note**: This is optional - rejection reasons can be displayed from event payloads without schema changes.

## Implementation Sequence (Time-Optimized)

### Phase 1: Core Functionality (2-3 hours)
1. **Collateral Refund Logic** - Modify batch runner event processing
2. **Basic Testing** - Verify refunds work for limit orders

### Phase 2: UI Enhancement (1-2 hours)  
1. **Rejected Orders Tab** - Add to portfolio view
2. **Basic Display** - Show rejected orders with reasons

### Phase 3: Admin Monitoring (1 hour)
1. **Rejection Metrics** - Add to admin dashboard
2. **Simple Counts** - Total rejections and rates

### Phase 4: Polish (Optional, if time remains)
1. **Error Handling** - Add basic error handling
2. **UI Improvements** - Better formatting and messages

## Risk Mitigation

### Low-Risk Approach
- **Leverage Existing Infrastructure**: Use existing event processing, order fetching, and UI components
- **Minimal Database Changes**: Avoid schema changes if possible
- **Incremental Implementation**: Each phase can be deployed independently
- **No Breaking Changes**: All modifications are additive

### Fallback Plan
If time runs short, implement only **Phase 1 (Collateral Refunds)** as this addresses the most critical user experience issue.

## Success Criteria

### Minimum Viable Implementation
- ✅ Rejected limit orders refund collateral to users
- ✅ Users can see their rejected orders in UI
- ✅ Admins can monitor rejection rates

### Demo-Ready State
- Users don't lose money on rejected orders
- Clear feedback when orders are rejected
- Admin can troubleshoot rejection issues

## Files to Modify Summary

1. **`app/runner/batch_runner.py`** - Add collateral refund logic
2. **`app/streamlit_app.py`** - Add rejected orders UI tab
3. **`app/streamlit_admin.py`** - Add rejection metrics
4. **`app/db/queries.py`** - Add helper functions for refunds (if needed)

## Estimated Implementation Time: 4-6 hours

This plan focuses on the essential functionality needed to make engine rejection handling work properly for the demo, while avoiding over-engineering and unnecessary complexity.
