#!/usr/bin/env python3
"""
Core Functionality Test

Quick test to verify that the core system still works after cleanup.
Tests the essential tax calculation flow using the new architecture.
"""

import decimal
from datetime import datetime
from pathlib import Path

import core
import transaction as tr
from tax_calculation.tax_service_factory import TaxServiceFactory


def test_basic_tax_calculation():
    """Test basic tax calculation flow."""
    
    # Create test operations
    buy_op = tr.Buy(
        platform="binance",
        utc_time=datetime(2023, 1, 1, 10, 0, 0),
        coin="BTC", 
        change=decimal.Decimal("1.0"),
        line=[1],
        file_path=Path("test.csv")
    )
    
    sell_op = tr.Sell(
        platform="binance",
        utc_time=datetime(2023, 6, 1, 10, 0, 0),
        coin="BTC",
        change=decimal.Decimal("0.5"),
        line=[2], 
        file_path=Path("test.csv")
    )
    
    operations = [buy_op, sell_op]
    
    # Create tax service
    tax_service = TaxServiceFactory.create_custom(
        tax_year=2023,
        country=core.Country.GERMANY,
        fiat_currency="EUR",
        multi_depot=False,
        principle=core.Principle.FIFO
    )
    
    # Evaluate operations
    tax_service.evaluate_operations(operations)
    
    # Verify results
    summary = tax_service.get_tax_summary()
    assert summary['calculation_completed'] == True
    assert summary['tax_year'] == 2023
    assert summary['country'] == 'GERMANY'
    
    # Check that entries were created
    entries = tax_service.get_tax_report_entries()
    assert isinstance(entries, list)
    
    # Check warnings
    warnings = tax_service.get_warnings()
    assert isinstance(warnings, list)
    
    print("✅ Basic tax calculation test passed!")


def test_migration_adapter():
    """Test that the migration adapter works."""
    
    from tax_calculation.taxman_integration import TaxmanMigrationAdapter
    
    # Create adapter
    adapter = TaxmanMigrationAdapter()
    
    # Create test operation
    buy_op = tr.Buy(
        platform="binance",
        utc_time=datetime(2023, 1, 1, 10, 0, 0),
        coin="BTC",
        change=decimal.Decimal("1.0"),
        line=[1],
        file_path=Path("test.csv")
    )
    
    # Test adapter interface
    adapter.add_operation(buy_op)
    adapter.evaluate_taxation()
    
    # Test compatibility properties
    entries = adapter.tax_report_entries
    assert isinstance(entries, list)
    
    summary = adapter.get_tax_summary()
    assert isinstance(summary, dict)
    assert 'calculation_completed' in summary
    
    print("✅ Migration adapter test passed!")


if __name__ == '__main__':
    try:
        test_basic_tax_calculation()
        test_migration_adapter()
        print("\n🎉 All core functionality tests passed!")
        print("The cleaned codebase is working correctly.")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        raise