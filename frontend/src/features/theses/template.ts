/** THS-07: structure of a new thesis, based on the former crypto/stocks statement.
 * A thesis may repeat the asset section for several assets. */
export const THESIS_TEMPLATE = `# Investment thesis

## Asset name (TICKER)

- **Role in portfolio**:
- **Expected holding period**:

### 1. Core thesis

Explain the long-term thesis in 2–5 sentences.

### 2. Why this asset (vs. alternatives)

Key differentiators and why this asset is preferred.

### 3. Value drivers

- Driver 1
- Driver 2

### 4. Risks

- Risk 1
- Risk 2

### 5. Break conditions

When one of these is met, set the thesis to *broken* and/or set exit flags in the policy.

- Condition 1
- Condition 2

### 6. Warning signals

Signals that weaken the thesis; when one is observed, the thesis needs adaptation. They trigger nothing by themselves.

- Signal 1
- Signal 2

### 7. Review checklist

- Metric / signal 1
- Metric / signal 2
`;
