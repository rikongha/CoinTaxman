# 🇩🇪 German Crypto Tax Compliance Reference - Living Document

> **Last Updated**: 2025-01-26  
> **Based on**: BMF Letter 6 Mar 2025, BFH ruling 14 Feb 2023, § 23/22/20 EStG  
> **Status**: Implementation Guide for CoinTaxman  

---

## 📋 **LEGAL FOUNDATIONS & SCOPE**

### **Core Legal Principle**
- **Crypto = "andere Wirtschaftsgüter"** (other economic assets) held privately
- **Disposals = private sales under § 23 EStG** (NOT Abgeltungsteuer)
- **Confirmed by**: Federal Fiscal Court (BFH, 14 Feb 2023, IX R 3/22)
- **Currency/Payment tokens**: Bitcoin, ETH, etc. explicitly covered

### **Three Tax Buckets (Implementation Required)**

| Tax Code | Category | Purpose | Freigrenze |
|----------|----------|---------|------------|
| **§ 23 EStG** | Private Veräußerungsgeschäfte | Crypto disposals within 1 year | €1,000 (2024+) |
| **§ 22 Nr. 3 EStG** | Sonstige Einkünfte (Leistungen) | Staking/lending/airdrops with consideration | €256 |
| **§ 20 EStG** | Kapitalvermögen | Derivatives/margin/futures | Various |

---

## 🎯 **TRANSACTION CLASSIFICATION MATRIX**

### **Critical Implementation Rules**

| Transaction Type | Tax Bucket | Key Rule | CoinTaxman Status |
|------------------|------------|----------|-------------------|
| **Buy (fiat→crypto)** | Acquisition only | Start holding period, set cost basis | ✅ Implemented |
| **Sell (crypto→fiat)** | § 23 | Taxable if <1yr, exempt if >1yr | ✅ Implemented |
| **Swap (crypto↔crypto)** | § 23 | Sale of outgoing at EUR FMV of incoming | ✅ Implemented |
| **Spend crypto on goods** | § 23 | Proceeds = EUR FMV of goods/service | ❓ Need to verify |
| **Passive staking reward** | § 22 Nr. 3 | Income at inflow/claiming | ✅ Implemented |
| **Lending interest/yield** | § 22 Nr. 3 | Income at access/credit | ✅ Implemented |
| **Airdrop WITH consideration** | § 22 Nr. 3 | Income at FMV at receipt | ❓ Classification logic needed |
| **Airdrop WITHOUT consideration** | Acquisition | €0 at receipt, taxed on later sale | ❓ Classification logic needed |
| **Hard fork** | Acquisition/cost split | Split cost by market-value ratio | ❌ Not implemented |
| **Wallet-to-wallet (same owner)** | Non-taxable | Must detect & link to avoid false disposals | ❓ Need verification |
| **Gifts/transfers to others** | § 23 | Taxable disposal | ❌ No Gift transaction type |

---

## 🧮 **CALCULATION METHODOLOGY**

### **1. Holding Period (Haltefrist)**
- **Rule**: Gains tax-free after >1 year (count from day after acquisition)
- **No 10-year extension** for payment tokens (BTC/ETH) - confirmed BMF 2025
- **CoinTaxman Status**: ✅ Correctly implemented (`relativedelta(years=1)`)

### **2. Proceeds & Cost Basis**
- **Fiat sale**: Agreed EUR price
- **Crypto-to-crypto**: EUR FMV of received asset at swap time
- **Cost basis**: Acquisition cost + directly related costs (exchange fees, gas)
- **UTXO change**: Retains original acquisition data (don't treat as new acquisition)

### **3. Inventory Method**
- **Per-wallet FiFo/Average**: Chosen method must be kept until wallet+asset fully depleted
- **After depletion**: Method switching allowed for new acquisitions
- **CoinTaxman Status**: ❓ Need to verify per-wallet method implementation

### **4. Freigrenzen (All-or-Nothing Thresholds)**
- **§ 23**: €1,000 annual net gain threshold (2024+)
  - If <€1,000: No tax
  - If ≥€1,000: Full amount taxable
- **§ 22 Nr. 3**: €256 annual net income threshold
  - Same all-or-nothing logic
- **CoinTaxman Status**: ✅ Both implemented

---

## 📊 **REPORT STRUCTURE REQUIREMENTS**

### **Summary Section Must Show**

#### **§ 23 EStG - Private Veräußerungsgeschäfte**
```
Gross gains €X / losses €Y → Net €N
Freigrenze €1,000: [Below/Above] threshold → Taxable amount €T
Transfer to Anlage SO 2024: lines 41-47 / 54-55 → €T
```

#### **§ 22 Nr. 3 EStG - Sonstige Einkünfte (Leistungen)**
```
Staking €A, Lending €B, Airdrops €C, Mining €D → Subtotal €S
- Direct costs €K = Net €M
Freigrenze €256 applied → Taxable amount €U
Transfer to Anlage SO 2024: lines 10-16 → €U
```

#### **§ 20 EStG - Kapitalvermögen**
```
Total P/L €P (derivatives/margin/futures)
Transfer to Anlage KAP 2024: lines 18-26a
```

#### **Unrealized Gains (Informational Only)**
```
FYI: Unrealized EOY delta vs. cost (Display only - not taxable)
```

### **Critical Separation Issues in CoinTaxman**
- **❌ CURRENT PROBLEM**: Realized and unrealized gains mixing in same categories
- **✅ REQUIRED FIX**: Strict separation with unrealized as informational only

---

## 🔍 **CURRENT COINTAXMAN ISSUES**

### **1. Category Structure Problems**
| Current Output | Issue | Required Fix |
|----------------|-------|--------------|
| `Einkünfte aus privaten Veräußerungsgeschäften: 15.71 EUR` | Shows 15.71 EUR but analysis shows 23,684.72 EUR | Unrealized gains mixed with realized |
| `Lending Zeitraum: 0.00 EUR` | Wrong category name | Should be part of § 22 Nr. 3 |
| `Unrealized gain: 23,669.01 EUR` | Inconsistent with detailed breakdown | Calculation discrepancy |

### **2. Missing Transaction Types**
- **❌ Gift/Transfer**: No transaction class for peer-to-peer gifts
- **❌ Hard Fork**: Not implemented
- **❌ Airdrop Classification**: No logic to distinguish with/without consideration

### **3. Report Format Issues**
- **❌ Form Mapping**: No clear mapping to Anlage SO lines
- **❌ Methodology Section**: Missing price sources, method disclosure
- **❌ EOY Holdings**: No end-of-year portfolio statement

---

## ✅ **IMPLEMENTATION CHECKLIST**

### **High Priority Fixes**
- [ ] **Fix realized vs unrealized mixing** in P&L categories
- [ ] **Add Gift transaction type** for peer-to-peer transfers
- [ ] **Implement airdrop classification logic** (with/without consideration)
- [ ] **Add hard fork support** with cost splitting
- [ ] **Create proper report structure** matching German tax forms

### **Report Structure Implementation**
- [ ] **Summary page** with three tax buckets and Anlage SO mapping
- [ ] **Detailed transaction ledger** (chronological with timestamps, TX-hash)
- [ ] **End-of-year holdings statement** (31 Dec 2024 valuation)
- [ ] **Methodology section** (FiFo/Average, price sources, day-price policy)
- [ ] **Staking claiming disclosure** (claimed vs unclaimed rewards)

### **Data Model Enhancements**
- [ ] **Per-wallet inventory method** selection with depletion-based switching
- [ ] **TX-hash tracking** for on-chain transactions
- [ ] **Price source audit trail** (exchange vs CoinMarketCap/CoinGecko)
- [ ] **Link ID system** for transfer legs and swap legs

### **German Tax Form Integration**
- [ ] **Anlage SO lines 41-47, 54-55** for § 23 disposals
- [ ] **Anlage SO lines 10-16** for § 22 Nr. 3 income
- [ ] **Anlage KAP lines 18-26a** for § 20 capital income

---

## 📚 **KEY REFERENCES**

### **Primary Sources**
- **BMF Letter (6 Mar 2025)** - Comprehensive crypto tax guidance
- **BFH Ruling (14 Feb 2023, IX R 3/22)** - Crypto as economic assets
- **§ 23 EStG** - Private sales (€1,000 Freigrenze from 2024)
- **§ 22 Nr. 3 EStG** - Other income (€256 Freigrenze)
- **Anlage SO 2024** - Official tax form structure

### **Implementation Examples**
- **Koinly reports** - Reference structure
- **Blockpit Germany** - Report format examples

---

## 🔄 **LIVING DOCUMENT UPDATES**

### **Version History**
- **2025-01-26**: Initial creation from comprehensive developer reference
- **Next Update**: After implementation fixes and testing

### **Key Takeaways for Development**
1. **Strict bucket separation** - § 23, § 22 Nr. 3, § 20 must never mix
2. **Unrealized gains** - Informational only, never taxable
3. **Form mapping** - Every category must map to specific Anlage SO/KAP lines
4. **Per-wallet methods** - FiFo/Average with depletion-based switching
5. **Documentation** - Price sources, methods, EOY holdings all required

---

*This document will be updated as implementation progresses and new requirements emerge.*