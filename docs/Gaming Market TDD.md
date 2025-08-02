# Technical Design Document: Gaming Market

## Design Goals
This document presents a self-contained technical design for an automated market maker (AMM) system optimized for high-volume speculation on events with multiple mutually exclusive outcomes, such as randomized AI agent competitions or hype-driven social games. The system treats each outcome as an independent binary market ("Will this outcome win? YES or NO"), enabling users to trade YES or NO tokens for each outcome. Each token redeems for exactly $1 in USDC if the bet is correct (e.g., holding 300 YES tokens for an outcome wins exactly $300 if that outcome occurs, and $0 otherwise), providing clear and predictable position sizing. The design prioritizes engaging gambling mechanics for Web3 "degens," fostering meme-like volatility and hype rather than accurate probability aggregation. Key features include tunable parameters for controlling price impacts within and across outcomes, allowing modes that amplify or dampen speculation dynamics.

The core goal is to create speculative assets that drive gambling volume while minimizing market maker risk. Accurate forecasting is explicitly not a priority; prices may deviate from rational probabilities to encourage irrational exuberance. The sum of prices across YES tokens for different outcomes is not enforced to equal $1, and the sum of YES and NO prices for a single outcome can exceed $1 to enable overround (house edge-like mechanics for volume monetization).

Key design goals:
- **Fixed Payouts**: Each YES or NO token redeems for exactly $1 in USDC if correct, ensuring straightforward risk-reward calculation.
- **User-Facing Prices in $0-$1**: Token prices are always less than $1, representing implied odds to appeal to speculators seeking excitement.
- **Phased Market Maker Risk**: The market maker provides an initial fixed subsidy that bounds maximum loss and decreases to zero as user-contributed liquidity grows, making launch risk-free after a threshold.
- **Hybrid Trading Support**: Users can execute immediate market orders (with tunable slippage) or place limit orders via a batched, pool-based limit-order book (LOB) for better depth and precision.
- **Multi-Outcome Compatibility**: Supports \( N > 2 \) mutually exclusive outcomes through independent binary markets, with tunable cross-coupling to make trades in one outcome inversely affect prices in others (e.g., buying YES for outcome A increases its price while decreasing YES prices for B and C).
- **Tunable Price Impacts**: Parameters control the strength of own-outcome price changes (e.g., how much buying YES A increases its price) and cross-outcome changes (e.g., how much it decreases other YES prices), enabling four modes:
  - High own impact, low cross impact.
  - Low own impact, high cross impact.
  - High own and cross impact.
  - Low own and cross impact.
- **Volume Monetization**: Asymmetry in buy/sell functions, fees, and convexity generate profits from trading activity in short-duration, random events.
- **No Trade Rejections**: All trades execute fully, with asymptotic slippage penalties making extreme buys prohibitively expensive and extreme sells yield near-zero returns, maintaining solvency without hard limits.
- **Cross-Matching YES/NO Limits**: Enable peer-to-peer matching between limit buys for YES and limit sells for NO (and vice versa) within the same binary outcome, treating them as complementary bets to aggregate opposing liquidity and tighten spreads, inspired by betting exchanges.
- **Auto-Filling on Cross-Impacts**: Automatically execute eligible limit orders against the AMM when cross-outcome trades shift prices, capturing seigniorage gains to reduce fees/penalties for large trades, with caps to prevent cascades.
- **Optional Multi-Resolution Support**: Configurable phased resolutions where losing outcomes are eliminated progressively across multiple rounds, with freed liquidity redistributed to remaining outcomes and YES prices adjusted via virtual supplies to maintain the pre-elimination sum of YES prices (increasing remaining YES prices proportionally), all while preserving solvency and allowing trading to pause/resume per round.

These enhancements foster deeper, more interactive markets by allowing direct user-to-user bets (cross-matching) and reactive liquidity recycling (auto-filling), amplifying hype and volume without unbounded risk. Cross-matching reduces fragmentation between YES/NO tokens, while auto-filling uses cross-impacts as triggers for opportunistic fills, generating system profits (seigniorage) to subsidize speculation. Solvency remains ensured via local \( L_i \) invariants, with total maker risk still bounded by Z.

This multi-resolution capability is optional and configurable at market creation. Market makers can specify a schedule of resolution rounds (e.g., eliminate 1 outcome per round over 4 rounds for \( N = 5 \)), or default to a single resolution round where all but one outcome are eliminated at once. When enabled, trading pauses before each resolution, an oracle eliminates specified outcomes, liquidity is reallocated, and YES prices are renormalized before trading resumes. The mechanism ensures that the sum of YES prices post-elimination equals the pre-elimination sum (across all outcomes), achieved via virtual YES additions that do not increase actual liabilities.

The system is designed for deployment on the SUI blockchain, leveraging its low gas fees and fast transaction times to support computational elements like quadratic solves. The design assumes an external oracle for event resolution and does not address disputes, focusing solely on the market mechanics. All math is derived from basic principles: solvency relies on the invariant that token supplies are less than effective pool sizes (ensuring payouts are covered), price changes use weighted averages for asymmetry (inspired by arithmetic means for closed forms), and impacts are tuned via fractions and weights consistent with ratio-based pricing.

## Definitions
### Symbols and Parameters
The system uses USDC as the base collateral asset. Each outcome i (1 to N) has an independent binary market with its own local effective pool, but trades couple across markets through diversion of collateral changes to other pools for inverse impacts. All prices and supplies are positive real numbers, and computations use fixed-point arithmetic for on-chain precision (e.g., 18 decimals for USDC).

#### Parameters Table
The following parameters are configurable at market creation, with defaults tuned for balanced speculation (e.g., moderate own impact, strong cross impact for hype amplification). Ranges are set to ensure solvency, positive impacts, and numerical stability.

| Parameter | Symbol | Type | Range/Default | Description |
|-----------|--------|------|---------------|-------------|
| Number of Outcomes | N | Integer | >2 / N/A | Number of mutually exclusive outcomes; creates N independent binary markets coupled via diversion.
| Initial Subsidy | Z | USDC Amount | >0 / 10,000 | Fixed USDC deposited by market maker to bootstrap liquidity; bounds maximum risk (allocated equally as Z/N per binary).
| Subsidy Phase-Out Rate | γ | Float | (0, 0.001) / 0.0001 | Rate at which subsidy per binary decreases with its local V_i (subsidy_i = max(0, Z/N - γ V_i)); reaches zero at V_i = (Z/N)/γ; range capped small to minimize intra-trade phase-out effects.
| Initial Virtual Supply | q0 | Float | >0 / (Z/N)/2 | Virtual tokens for YES and NO in each binary to seed initial prices at $0.5 each (ensures p_yes = p_no = q0 / L_i = 0.5, sum =1).
| Initial Weight | μ | Float | >0 / 1 | Weight on initial price in the asymmetric average for buys/sells (higher μ favors stronger own impact by reducing collateral addition).
| New Weight | ν | Float | >0 / 1 | Weight on new price in the asymmetric average (higher ν favors stronger cross impact by increasing collateral addition).
| Convexity Parameter | κ | Float | >=0 / 0.001 | Controls additional slippage for large trades (higher κ increases both own and cross impacts for large sizes).
| Cross Coupling Fraction | ζ | Float | (0, 1/(N-1)) / 0.1 | Fraction of collateral addition diverted to other binaries' pools on buys/sells (higher ζ strengthens cross impact; capped to ensure positive local addition).
| Fee Fraction | f | Float | (0,0.05) / 0.01 | Fraction of trade value collected as fee for the market maker.
| Maximum Price | p_max | Float | (0.5,1) / 0.99 | Soft cap for asymptotic slippage on buys (p' approaches p_max, cost → ∞).
| Minimum Price | p_min | Float | (0,0.5) / 0.01 | Soft floor for asymptotic slippage on sells (p' approaches p_min, received → 0).
| Penalty Exponent | η | Float | >1 / 2 | Factor for inflating/deflating slippage penalties when exceeding p_max/p_min.
| Tick Granularity | tick_size | Float | >0 / 0.01 | Price increments for LOB in $0-$1 scale (e.g., pools at $0.01, $0.02, ..., $0.99).
| Cross-Match Enabled | cm_enabled | Boolean | True/False / True | Flag to enable YES/NO cross-matching in the LOB per binary; if false, reverts to siloed pools.
| Match Fee Fraction | f_match | Float | (0,0.02) / 0.005 | Fraction of matched value collected as fee on cross-matches (split between sides).
| Auto-Fill Enabled | af_enabled | Boolean | True/False / True | Flag to enable auto-filling on cross-impacts; opt-in per limit order via flag.
| Seigniorage Share | σ | Float | [0,1] / 0.5 | Fraction of seigniorage gains allocated to system (remainder to users as rebates); 0 means full price improvement.
| Auto-Fill Volume Cap Fraction | af_cap_frac | Float | (0,0.2) / 0.1 | Fraction of diverted collateral (ζ * X) limiting max filled Δ per pool.
| Max Pools per Auto-Fill | af_max_pools | Integer | 1-5 / 3 | Cap on number of pools auto-filled per cross-event to prevent cascades.
| Max Surplus per Trade | af_max_surplus | Float | >0 / 0.05 | Cap on total seigniorage as fraction of triggering trade size (X).
| Multi-Resolution Enabled | mr_enabled | Boolean | True/False / False | Flag to enable multi-resolution phased eliminations; if false, reverts to single final resolution.
| Resolution Schedule | res_schedule | Array of Integers | [] / [] | Array specifying outcomes eliminated per round (e.g., [1,1,1,1] for 4 rounds eliminating 1 each in N=5); sum must equal N-1; empty for single resolution.
| Virtual Cap Enabled | vc_enabled | Boolean | True/False / True | Flag to cap virtual_yes_i at 0 if computed negative during renormalization (prevents underflow).

#### Key Variables (Per Binary Market i)
- \( V_i \): Local user-contributed USDC pool for binary i, starts at 0, increases on buys and decreases on sells (monotonic net over time due to asymmetry).
- Subsidy_i: Effective subsidy = \( \max(0, Z/N - \gamma V_i) \).
- \( L_i \): Local effective pool = \( V_i + \) subsidy_i.
- \( q_{\text{yes}_i} \): Circulating supply of YES tokens for outcome i (starts at q0).
- \( q_{\text{no}_i} \): Circulating supply of NO tokens for outcome i (starts at q0).
- \( p_{\text{yes}_i} \): Price of YES i = \( q_{\text{yes}_i} / L_i < p_{\max} \).
- \( p_{\text{no}_i} \): Price of NO i = \( q_{\text{no}_i} / L_i < p_{\max} \).
- Sum_i: \( p_{\text{yes}_i} + p_{\text{no}_i} = (q_{\text{yes}_i} + q_{\text{no}_i}) / L_i \) (can ≥1 due to asymmetry).
- Seigniorage_i: Accumulated surplus USDC from auto-fills in binary i, used to offset fees/penalties.
- virtual_yes_i: Virtual YES supply for outcome i (starts at 0, adjusted post-elimination to renormalize prices; affects pricing but not payouts).
- active_i: Boolean flag indicating if binary i is still active (starts true; set false on elimination).
- pre_sum_yes: Global variable tracking the sum of p_yes across all outcomes before each resolution (updated pre-pause).

#### Key Concepts
- **YES i Token**: An ERC20-compatible token representing a bet that outcome i wins; redeems for $1 USDC per token if i wins, $0 otherwise.
- **NO i Token**: An ERC20-compatible token representing a bet that outcome i does not win; redeems for $1 USDC per token if i loses, $0 if i wins.
- **Market Order**: An immediate trade executed first against the LOB (if matches available), then the AMM for the remainder, with slippage controlled by parameters.
- **Limit Order**: A queued contribution to a price-increment pool in the LOB at a specified price, matched pro-rata against opposing market orders for better execution.
- **Own Impact**: The change in price within the traded binary (e.g., buying YES i increases \( p_{\text{yes}_i} \)); tuned by μ (higher favors stronger own by reducing collateral addition) and ν (higher favors weaker own by increasing collateral addition).
- **Cross Impact**: The change in prices in other binaries (e.g., buying YES i decreases \( p_{\text{yes}_j} \) for j != i); tuned by ζ (fraction diverted to other L_j, higher = stronger cross).
- **Asymmetry**: Buys use a weighted average favoring initial price (premium), sells favor new price (discount), creating spreads for maker profit and allowing sum ≥1.
- **Asymptotic Slippage**: For trades pushing p' > p_max on buys, inflate cost X to ∞; for p' < p_min on sells, deflate received X to 0, ensuring solvency without rejections.
- **Diversion**: On trades in binary i, a fraction ζ of the collateral change is added/subtracted from each other L_j (j != i), creating inverse impacts without affecting solvency (total V changes by the full amount).
- **Overround**: The condition \( p_{\text{yes}_i} + p_{\text{no}_i} \geq 1 \), achieved through asymmetry (buys push sum up, sells down), encouraging speculation by implying "edge" but monetized via fees.
- **Batched LOB**: All limit orders are pooled per price increment ($0.01 steps), batched per block for matching to mitigate MEV (e.g., pro-rata fills on market orders, fees applied on fills).
- **YES/NO Cross-Matching**: A mechanism in the LOB where limit buys for YES i at price P match with limit sells for NO i at complementary price ~1 - P (adjusted for asymmetry), minting tokens backed by combined collateral.
- **Auto-Filling**: Triggered execution of opt-in limit pools against the AMM on cross-impacts, computing fills to respect tick prices and capturing surplus as seigniorage.
- **Seigniorage Gains**: Surplus collateral from filling at AMM price < tick (for buys) or > tick (for sells), allocated per σ to system (extra V_i) and users (rebates).
- **Multi-Resolution Round**: A phased event where trading pauses, an oracle eliminates specified losing outcomes (paying NO holders), freed liquidity is redistributed equally to remaining active binaries, and virtual_yes is adjusted for remaining YES prices to sum to the pre-round total sum_yes (proportionally increasing each p_yes).
- **Freed Liquidity**: For eliminated outcome k, \( L_k - q_{\text{no}_k} \) (after paying \( q_{\text{no}_k} \) to NO holders).
- **Renormalization**: Post-redistribution, compute target \( p_{\text{yes}_j} = (\text{old } p_{\text{yes}_j} / \text{post_redist_sum_remaining}) \times \text{pre_sum_yes} \) for each remaining j; set virtual_yes_j = target \( p_{\text{yes}_j} \times \) updated \( L_j - q_{\text{yes}_j} \) (capped at max(0, ...) if vc_enabled).
- **Effective YES Supply**: \( q_{\text{yes_eff}_i} = q_{\text{yes}_i} + \) virtual_yes_i, used in all YES pricing, trading, and impact formulas (e.g., \( p_{\text{yes}_i} = q_{\text{yes_eff}_i} / L_i \)); actual \( q_{\text{yes}_i} \) used only for payouts.

## Derivations & Proofs
### Price Definition and Sum Dynamics
The price for YES i is \( p_{\text{yes}_i} = (q_{\text{yes}_i} + \text{virtual_yes}_i) / L_i = q_{\text{yes_eff}_i} / L_i \), where virtual_yes_i >=0. Similarly for \( p_{\text{no}_i} = q_{\text{no}_i} / L_i \) (unchanged). This ensures p_yes <1 as long as q_yes_eff < L_i (enforced by penalties). The sum for binary i is \( p_{\text{yes}_i} + p_{\text{no}_i} = (q_{\text{yes_eff}_i} + q_{\text{no}_i}) / L_i \). The asymmetry in the cost function ensures this sum can exceed 1 on buys (X < Δ * (p + p') /2 for μ >ν, L_i up less than expected, sum up) and drop below on sells, but parameters can be tuned to favor ≥1 on net for overround.

Proof that sum ≥1 is achievable: Assume initial sum =1 (\( q_{\text{yes}} + q_{\text{no}} = L_i \)). On buy Δ YES, \( X = \Delta (\mu p + \nu p') / (\mu + \nu) + \kappa \Delta^2 \), \( p' = (q_{\text{yes}} + \Delta) / (L_i + f_i X) \), \( f_i = 1 - (N-1)\zeta \). If μ >ν, X < Δ (p + p') /2, \( f_i X < \Delta (p + p') /2 \), sum' = \( (q_{\text{yes}} + \Delta + q_{\text{no}}) / (L_i + f_i X) >1 \) if \( f_i X < \Delta \). For example, with μ=2, ν=1, κ=0, f_i=0.5 (N=3, ζ=0.25), numerical solve shows sum' >1 for Δ >0.

### Buy Cost Function (YES i)
The cost X for buying Δ YES i satisfies:
\[
X = \Delta \frac{\mu p + \nu p'}{\mu + \nu} + \kappa \Delta^2
\]

\[
p' = \frac{q_{\text{yes}} + \Delta}{L_i + f_i X}
\]

where \( f_i = 1 - (N-1) \zeta \) (local fraction, remainder diverted).

Substitute p':
Let \( a = \mu / (\mu + \nu) \), \( b = \nu / (\mu + \nu) \)
\( X - \kappa \Delta^2 = \Delta a p + \Delta b (q_{\text{yes}} + \Delta) / (L_i + f_i X) \)

Let \( k = \Delta a p + \kappa \Delta^2 \)
\( m = \Delta b (q_{\text{yes}} + \Delta) \)
\( X - k = m / (L_i + f_i X) \)
\( (X - k) (L_i + f_i X) = m \)
\( f_i X^2 + L_i X - f_i k X - k L_i = m \)
\( f_i X^2 + (L_i - f_i k) X - k L_i - m = 0 \)

Quadratic coefficients: coeff_a = f_i, coeff_b = L_i - f_i k, coeff_c = -k L_i - m

Solution (positive root):
\[
X = \frac{ - \text{coeff}_b + \sqrt{\text{coeff}_b^2 - 4 \text{coeff}_a \text{coeff}_c} }{2 \text{coeff}_a}
\]

Proof of existence/positivity: Discriminant = \( (L_i - f_i k)^2 + 4 f_i (k L_i + m) >0 \) (all terms ≥0). Since sqrt > |coeff_b| (for coeff_b >0, discriminant > coeff_b^2), X >0.

To approximate subsidy phase-out in solve (as γ small), subtract γ * f_i * X_guess from L_i in each Newton iteration if needed, but with γ capped low, effect negligible (<0.001 overrun).

Then, update V_i += f_i * X (after fee deduction), V_j += ζ * X for j != i.

### Sell Received Function (YES i)
The received X for selling Δ YES i satisfies:
\[
X = \Delta \frac{\mu p' + \nu p}{\mu + \nu} - \kappa \Delta^2
\]

\[
p' = \frac{q_{\text{yes}} - \Delta}{L_i - f_i X}
\]

Similar quadratic: Substitute, solve positive root.

Diversion: V_j -= ζ * X for j !=i.

### Asymptotic Penalty
After solving X, p':
If p' > p_max on buy, X *= (p' / p_max)^η (inflate cost).
If p' < p_min on sell, X *= (p_min / p')^η (deflate received).

Proof of no rejection: System always has positive root; penalty adjusts X without preventing execution.

### Cross-Matching Mechanics
For binary i, a limit buy YES at tick T (USDC deposited) matches with limit sell NO at tick S if T + S ≈ 1 + overround adjustment (e.g., T ≥ 1 - S + f_match/2). On match:

**Limit Price Enforcement**: Users are guaranteed their specified limit prices:
- YES buyer pays exactly T per token (their limit price)
- NO seller receives exactly S per token (their limit price)
- Trading fees are applied separately and transparently

**Execution Details**:
- YES buyer contributes: T * Δ (USDC at their limit price)
- NO seller contributes: S * Δ (via tokens burned at their limit price)
- Total system collateral: (T + S) * Δ
- Fee: f_match * (T + S) * Δ / 2 (split between maker and taker)
- Net collateral to V_i: (T + S) * Δ - fee = (T + S - f_match * (T + S) / 2) * Δ
- Update \( q_{\text{yes}_i} += \Delta \), \( q_{\text{no}_i} += \Delta \)

**User Experience**:
- Limit orders execute at-or-better than specified prices
- Fees are clearly separated from execution prices
- No surprise pricing due to pooled collateral effects
- Traditional limit order book expectations are preserved

Proof of solvency preservation: Net collateral (T + S - f_match * (T + S) / 2) * Δ ≥ Δ when T + S ≥ 1 + f_match * (T + S) / 2, ensuring \( q_{\text{yes}_i} + q_{\text{no}_i} < 2 L_i \).

### Auto-Filling and Seigniorage
On cross-impact (e.g., diversion ζ * X to L_j, dropping p_yes_j), for opt-in buy pools in j (ticks > new p_yes_j):
- Iterate highest to lowest tick: Compute max Δ s.t. p' ≤ tick via binary search (5-10 iterations: low=0, high=pool_volume / p, mid solve via quadratic).
- X = buy_cost(Δ), charge = tick * Δ, surplus = charge - X.
- If surplus >0, system gets σ * surplus (add to V_j), user gets (1-σ) * surplus as rebate or bonus tokens.
- Cap Δ ≤ af_cap_frac * ζ * X_trigger, total pools ≤ af_max_pools, total surplus ≤ af_max_surplus * X_trigger.
- Triggering trade (in i) repriced at final stabilized prices (post all auto-fills), with penalty reduced by system seigniorage share (η effective -= seigniorage / X_trigger).

Proof of no cascades: Caps bound fills; batching ensures sequential processing per block. Invariant: Surplus ≥0 adds to V_j without inflating q beyond L_j.

### Solvency Proof
Invariant: \( p_{\text{yes}_i} < p_{\max} <1 \) => \( q_{\text{yes}_i} < p_{\max} * L_i < L_i \) (similar for NO).

Payout for binary i: max(\( q_{\text{yes}_i} \), \( q_{\text{no}_i} \)) < L_i.

Since \( L_i = V_i + \) subsidy_i, payout < L_i, covered locally.

Proof by induction: Initial p=0.5 < p_max. On trade, if p' > p_max, penalty increases X on buy (L_i up more, p' down), or decreases X on sell (L_i down less, p' up), preserving q < p_max * L'. 

Diversion affects other L_j (increasing on buy, decreasing on sell), but each binary's invariant holds independently.

Maker loss per binary <= subsidy_i <= Z/N, total <= Z.

Extend induction: Cross-matches add balanced collateral; auto-fills use standard solves with penalties, preserving q < p_max * L'. Seigniorage adds extra V_i, strengthening coverage (payout < L_i + seigniorage_i).

### Multi-Resolution Solvency and Dynamics Proofs
Invariant Extension: Actual liabilities remain max(\( q_{\text{yes}_i} \), \( q_{\text{no}_i} \)) < L_i, as virtual_yes_i affects only effective pricing (not payouts). Post-elimination, freed = \( L_k - q_{\text{no}_k} \) >= \( q_{\text{yes}_k} \) (since \( q_{\text{yes}_k} + q_{\text{no}_k} < 2 L_k \) initially, but post-payout covers only NO). Redistribution: added = freed / remaining >0, increasing each L_j without changing \( q_{\text{yes}_j} \) or \( q_{\text{no}_j} \), thus strengthening coverage.

Renormalization Proof: Target sum = pre_sum_yes. Since post_redist_sum_remaining < pre_sum_yes (due to L_j increase without q_yes_eff change), targets > old p_yes_j, yielding virtual_yes_j >0. If any negative (edge asymmetry), cap at 0 preserves sum <= pre_sum_yes but ensures no underflow. Trading post-renorm: Penalties enforce q_yes_eff' < p_max L_j => \( q_{\text{yes}_i} + \Delta + \) virtual_yes_i < p_max L_j < L_j, so actual \( q_{\text{yes}_i} + \Delta < L_j - \) virtual_yes_i <= L_j.

Multi-Round Induction: Base (single round) as original. Inductive: Each round preserves invariants locally; final payout uses actual q (covered by accumulated V + subsidy). Total maker risk still <= Z, as freed liquidity recycles within system.

### Instability Proof
Asymmetry and coupling create positive feedback for volatility.

Stochastic model: Trades prob ε, size κ q, σ= +1 (buy), -1 (sell).

On buy YES i: X ~ Δ (average p), L_i up f_i X, p' ~ p (1 + κ) / (1 + f_i X / L_i)

If μ >ν, average < p', X < Δ p', L up < Δ p', p' > p (1 + κ /2)

Cross: L_j up ζ X, p_j down ~ ζ κ

Expected L growth E[L] ~ L (1 + ε κ (average / p - 1/2)) >L if average > p/2.

Drift μ = ε κ ln(1 + average / p) >0

Variance ~ ε κ^2 n

Lyapunov χ = ε ln(1 + κ) >0, tunable by ζ (higher = stronger cross, amplification).

Proof: Disagreement causes exponential p divergence, rate χ >0 unless ε=0.

## Technical Implementation
### Initialization
- Maker transfers Z USDC, allocated subsidy_i = Z/N.
- For each i: V_i =0, L_i = subsidy_i, \( q_{\text{yes}_i} = q_{\text{no}_i} = q0 \), \( p_{\text{yes}_i} = p_{\text{no}_i} = q0 / L_i =0.5 \).
- Deploy YES i and NO i ERC20 tokens.
- seigniorage_i =0.
- virtual_yes_i = 0; active_i = true; pre_sum_yes = sum(p_yes across all i) = N * 0.5 (initially).

### Pseudocode for Buy YES i (Market Order, Δ tokens)
```python
def buy_yes(i, Δ):
    # Cross-matching first (if cm_enabled)
    matched_cross = 0
    cost_cross = 0
    if cm_enabled:
        for tick_yes in ticks_above(p_yes_i):  # Scan complementary NO sell pools
            comp_tick_no = int(1 / tick_size - tick_yes)  # Approximate complement
            pool_no = get_sell_pool(i, NO, comp_tick_no)
            if pool_no.volume >0 and tick_yes + comp_tick_no * tick_size >=1:
                fill = min(Δ - matched_cross, pool_no.volume)
                price_yes = tick_yes * tick_size  # YES buyer's limit price
                price_no = comp_tick_no * tick_size  # NO seller's limit price
                
                # True limit price enforcement: users pay/receive exactly their limit prices
                cost_cross += fill * price_yes  # YES buyer pays their limit price
                # NO seller receives their limit price (handled in pool settlement)
                
                matched_cross += fill
                update_pool_fill(pool_no, fill, buy=False)  # Burn NO, mint YES
                
                # Fee calculation per TDD: f_match * (T + S) * Δ / 2 (split between sides)
                fee_cross = f_match * fill * (price_yes + price_no) / 2
                
                # System collateral: total user contributions minus fee
                V_i += (price_yes + price_no) * fill - fee_cross

    # LOB matching (batched per block)
    matched = 0
    cost_lob = 0
    current_price = q_yes_i / L_i
    for tick in ticks_above(current_price):  # Batched scan high to low
        pool = get_sell_pool(i, YES, tick)
        if pool.volume >0:
            fill = min(Δ - matched, pool.volume)
            price = tick * tick_size
            cost_lob += fill * price
            matched += fill
            # Pro-rata: Users in pool get filled position (tokens or USDC)
            update_pool_fill(pool, fill, buy=True)  # Fee f * fill * price to maker

    # AMM for remaining
    remaining = Δ - matched
    if remaining >0:
        p = q_yes_eff_i / L_i
        q = q_yes_eff_i
        L = L_i
        f_i = 1 - (N_active - 1) * ζ
        # Quadratic solve
        k = remaining * μ * p / (μ + ν) + κ * remaining**2
        m = remaining * ν * (q + remaining) / (μ + ν)
        coeff_a = f_i
        coeff_b = L - f_i * k
        coeff_c = -k * L - m
        disc = coeff_b**2 - 4 * coeff_a * coeff_c
        X = (-coeff_b + math.sqrt(disc)) / (2 * coeff_a)
        p_prime = (q + remaining) / (L + f_i * X)
        if p_prime > p_max:
            X *= (p_prime / p_max)**η
            p_prime = (q + remaining) / (L + f_i * X)
        cost_amm = X
        fee = f * remaining * p_prime
        total_user_payment = cost_amm + fee
        # Update local
        V_i += f_i * X
        subsidy_i = max(0, Z / N - γ * V_i)
        L_i = V_i + subsidy_i
        q_yes_i += remaining
        # Diversion to cross
        for j in range(N):
            if j != i:
                V_j += ζ * X
                subsidy_j = max(0, Z / N - γ * V_j)
                L_j = V_j + subsidy_j

    # Auto-filling on diversion (post all updates, batched)
    if af_enabled:
        for j in range(N):
            if j != i:
                auto_fill_batch(j, diversion_amount=ζ * X, is_increase=True)  # For price drop

    mint_yes(i, Δ)
    transfer_usdc(user, - (cost_lob + total_user_payment))

def auto_fill_batch(j, diversion_amount, is_increase):
    seigniorage_total = 0
    pools_filled = 0
    if is_increase:  # Price drop: auto-buy pools
        sorted_buy_pools = get_buy_pools_above(j, YES, p_yes_j) + get_buy_pools_above(j, NO, p_no_j)  # Highest tick first
        for pool in sorted_buy_pools:
            if pools_filled >= af_max_pools: break
            C = pool.usdc_volume
            tick = pool.tick * tick_size
            # Binary search for max Δ s.t. p' <= tick
            low, high = 0, C / p_yes_j  # Or p_no_j
            for _ in range(10):
                mid = (low + high) / 2
                X_mid = buy_cost(mid)  # Quadratic
                p_mid = (q + mid) / (L_j + f_j * X_mid)
                if p_mid <= tick:
                    low = mid
                else:
                    high = mid
            Δ = min(low, af_cap_frac * diversion_amount)
            if Δ >0:
                X = buy_cost(Δ)
                charge = tick * Δ
                surplus = charge - X
                if surplus > af_max_surplus * diversion_amount: surplus = af_max_surplus * diversion_amount; Δ *= (X + surplus) / charge  # Adjust
                V_j += σ * surplus  # System extra collateral
                rebate_users(pool, (1 - σ) * surplus)  # Pro-rata
                mint_tokens(j, Δ, is_yes=pool.is_yes)
                update_pool_fill(pool, Δ, buy=True)
                seigniorage_total += surplus
                pools_filled +=1
    # Symmetric for !is_increase (price rise: auto-sell pools)
    # Reprice triggering trade at new prices, reduce penalty by seigniorage_total
    adjust_triggering_trade(i, new_penalty=original_penalty - seigniorage_total / X_trigger)
```

### Sell YES i (Δ tokens)
Similar to buy, but use sell equation for X, diversion V_j -= ζ * X (cross p_j up), total_user_receive = X - f * Δ * p_prime.

### Limit Order Placement/Matching
- Placement: Add USDC (for buy pools) or tokens (for sell pools) to pool at tick = d_limit / tick_size (e.g., $0.50 = tick 50).
- Pools: Table of pools at ticks 1 to 99 ($0.01 to $0.99); each pool tracks total volume and user shares (mapping user to share).
- Matching: Batched per block: For market buys, fill from lowest sell pool above current price pro-rata; users in pool receive USDC minus fee. Similar for sells from highest buy pool below price. Filled amount updates shares; withdrawals claim pro-rata filled/unfilled.
- Cancellation: Withdraw unfilled share anytime, pro-rata of remaining pool.
- MEV Mitigation: All orders batched per block, matched FIFO in batch.
- Update to include cross-matching in batch processing.
- Add opt-in flag to placement: placeLimit(..., bool af_opt_in).

```python
def resolution_round(round_num):
    if not mr_enabled: return  # Skip if single-res
    pause_trading()  # Halt buys/sells/limits
    elim_count = res_schedule[round_num]
    eliminated = oracle_get_eliminated(elim_count)  # List of i to eliminate
    pre_sum_yes = sum(p_yes_j for j active)  # Update if needed
    for k in eliminated:
        if not active_k: revert
        payout_no_k = q_no_k  # Send $1 per NO_k to holders from L_k
        V_k -= payout_no_k  # Or L_k, but subsidy phase-out unaffected
        freed = L_k - payout_no_k  # Now L_k = V_k + subsidy_k - payout_no_k, but since YES_k worthless, freed = remaining L_k - payout_no_k
        burn_yes_no_k()  # Burn all tokens for k
        active_k = false
    remaining = count(active)
    if freed > 0 and remaining > 1:
        added = freed / remaining
        for j active:
            V_j += added
            L_j = V_j + subsidy_j  # Recompute
    # Renormalize
    post_redist_sum = sum(p_yes_j for j active)  # Using current virtual
    for j active:
        target_p = (p_yes_j / post_redist_sum) * pre_sum_yes if post_redist_sum > 0 else p_yes_j
        virtual_yes_j = target_p * L_j - q_yes_j
        if vc_enabled and virtual_yes_j < 0: virtual_yes_j = 0
    resume_trading()  # Resume after updates
```

### Resolution and Redemption
- Oracle signals winner w, triggering burn-and-claim.
- System burns all tokens.
- For binary w: Send $1 per YES w token to holders from L_w; NO w gets $0.
- For binary j != w: Send $1 per NO j token to holders from L_j; YES j gets $0.
- Remaining in each L_i sent to market maker.
- Remaining seigniorage_i to market maker.
- For final resolution (after all rounds or single): Oracle signals winner w (last remaining). For w: Pay $1 per actual q_yes_w (not virtual). For all j != w (eliminated earlier): Already paid NO_j in prior rounds; YES_j = $0. Remaining L_i to maker.

### Edge Cases and Invariants
- Oversized buy: p_prime → p_max, X →∞, executes.
- Oversized sell: p_prime → p_min, X →0, executes.
- Diversion cap: ζ <1/(N-1) ensures f_i >0.
- Zero subsidy: Trades continue, risk 0.
- Concurrency/MEV: Batch per block, FIFO matching.
- Numerical: Fixed-point (18 decimals), Babylonian sqrt (3-5 iter for disc).
- Intra-trade phase-out: γ capped low; approximate in solve by reducing L = L - γ * f_i * X_guess in iterations (negligible effect).
- Invariants: p < p_max, q < p_max * L_i, V_i >=0, total loss <= Z.
- Multi-round extreme: Sequential elims preserve q_actual < L (as per proofs). - Negative virtual: Capped, sum may < pre but solvency holds. - Single round: res_schedule empty, direct to final.

## Interface
- **Assets**: YES i and NO i ERC20 tokens for each outcome.
- **Market Order**: Functions buyYes(uint i, uint Δ) and buyNo(uint i, uint Δ); returns tokens.
- **Limit Order**: placeLimit(uint i, uint amount, uint d_limit, bool isYes, bool isBuy); adds to pool (amount in USDC/tokens).
- Withdraw Limit: withdrawFromPool(uint i, uint tick, bool isYes, bool isBuy); claims pro-rata.
- Add params to market creation (e.g., cm_enabled).
- Extend placeLimit with af_opt_in flag.
- Market Creation: Add params mr_enabled, res_schedule, vc_enabled.
- New: triggerResolutionRound(uint round_num)  # Callable by oracle/maker, executes above.
- Redemption: Update to handle phased payouts.

## Limit Order Pricing and User Experience

### True Limit Price Enforcement
The system implements **Option 1: True Limit Price Enforcement** where:
- **YES buyers** pay exactly their limit price in USDC
- **NO sellers** receive exactly their limit price in USDC  
- **Trading fees** are applied separately and transparently
- **Execution guarantee**: Orders execute at-or-better than specified limit prices

### Fee Structure
- Cross-matching fee: `f_match * (price_yes + price_no) * fill / 2`
- Fee is **split between maker and taker** (each pays half)
- Fees are **separate from limit prices**, maintaining traditional limit order expectations
- Total system collateral: `(price_yes + price_no) * fill - fee`

### User Experience Benefits
1. **Predictable Costs**: Users know exactly what they'll pay/receive
2. **Traditional Behavior**: Matches expectations from other limit order books
3. **Transparent Fees**: Trading costs are clearly separated from execution prices
4. **Fair Matching**: Overround creates house edge without double-charging users

### Mathematical Properties
- **Solvency Preserved**: System maintains `V_i ≥ 0` through proper fee accounting
- **Overround Maintained**: `price_yes + price_no ≥ 1.00` creates gambling excitement
- **Fee Revenue**: Split fees provide sustainable revenue model
- **Arbitrage Bounds**: Cross-matching only occurs when profitable for both sides

## User Implications/Dynamics
- **Fixed Payout Certainty**: Trades execute, 300 tokens pay $300 if correct; asymptotic warnings for extremes.
- **Prices in $0-$1**: p <1; asymmetry allows sum YES/NO ≥1 for overround excitement.
- **Speculation Excitement**: Tunable modes create volatility (e.g., high own/low cross for isolated pumps, high cross for chain reactions).
- **Shorting**: Buy NO i decreases p_yes_i like short, increases p_no_i.
- **Cross Effects**: Buy YES i decreases other YES prices for inverse dynamics, tunable for game-like interactions.
- **Orders**: Market with slippage; batched LOB for pro-rata depth.
- Cross-matching enables exchange-like betting, reducing slippage; auto-filling clears stale orders during hype, with seigniorage making large trades cheaper (penalties reduced up to caps).
- In multi-res, YES prices increase post-elim (sum preserved), boosting hype; NO prices decrease. Trading pauses briefly per round.

## Market Maker Implications/Dynamics
- **Profit Mechanisms**: Fees f on trades and LOB fills.
- **Risk Profile**: Bounded by Z, phases to 0 per binary as V_i grows (e.g., zero at ~10k V total).
- **Instability Benefit**: Coupling amplifies hype, boosting volume/fees without unbounded risk.
- **Operational**: Tune μ,ν,κ,ζ for modes; monitor V_i for phase-out. SUI low gas supports solves/loops.
- Additional fees from f_match; seigniorage as extra V_i profits, bounded by caps; monitor af_max_pools for volatility control.
- Optional multi-res recycles liquidity, potentially increasing volume over phases; tune schedule for event pacing. Risk still bounded by Z.

# Addendum: Dynamic Parameter Tuning for Linear Transition

## Overview
This addendum describes the implementation of linear interpolation for tuning parameters (\( \zeta \), \( \mu \), \( \nu \), \( \kappa \)) from starting values (e.g., High Own/High Cross mode) to ending values (e.g., High Own/Low Cross mode) as the market approaches the scheduled resolution time \( T \). This approach enables smooth mode transitions to maximize engagement and volume while preserving solvency guarantees, provided parameters remain within safe ranges.

## Tunable Parameters and Safe Ranges
- \( \zeta \) (cross-coupling fraction): Interpolate within \( (0, 1/(N-1)) \), e.g., from 0.1 to 0.01.
- \( \mu \) (initial price weight): Interpolate within >0, e.g., from 2 to 1.5 (or constant at 2).
- \( \nu \) (new price weight): Interpolate within >0, e.g., constant at 1.
- \( \kappa \) (convexity parameter): Interpolate within ≥ 0, e.g., from 0.001 to 0.0005.

Other parameters (e.g., \( f \), \( \eta \), \( p_{\max} \), \( p_{\min} \)) remain static to avoid destabilizing penalties or fees.

## Implementation Considerations
- **Interpolation Formula**: For parameter \( p \), \( p(t) = p_{\text{start}} + \frac{t}{T} (p_{\text{end}} - p_{\text{start}}) \), where \( t \) is the current timestamp minus market creation timestamp.
- **Update Mechanism**: Recompute parameters on-chain per block or at fixed intervals (e.g., every 1% of \( T \)) using the contract's current timestamp. Use in trade functions (e.g., buy/sell quadratics) and pricing queries.
  - Example for \( \zeta \): \( \zeta(t) = 0.1 - 0.09 \cdot \frac{t}{T} \).
- **Numerical Precision**: Use fixed-point arithmetic (18 decimals) for \( t/T \) calculations to avoid floating-point errors. Clamp \( p(t) \) to safe ranges (e.g., \( \zeta(t) \leq 0.1 \)).
- **Multi-Resolution Support**: If mr_enabled = True, reset interpolation per round (e.g., restart \( t = 0 \) at each round's start, decreasing \( \zeta \) to ending value by round's end).
- **Edge Cases**: 
  - At \( t = 0 \): Use \( p_{\text{start}} \).
  - At \( t \geq T \): Lock at \( p_{\text{end}} \); pause trading before resolution.
  - Ensure \( f_i(t) = 1 - (N-1)\zeta(t) > 0 \) in all solves to prevent division errors.
- **Monitoring**: Log parameter values per trade for debugging; simulate interpolation off-chain to verify volume impacts.

## Solvency Assurance
Solvency invariants (\( q_{\text{yes}_i}, q_{\text{no}_i} < p_{\max} L_i < L_i \)) hold via asymptotic penalties and local pool updates, independent of specific parameter values within safe ranges. The quadratic solve remains valid (positive discriminant), and diversion preserves total collateral. Induction proof extends to dynamic parameters, as each trade enforces bounds regardless of \( t \). Risk remains bounded by \( Z \).