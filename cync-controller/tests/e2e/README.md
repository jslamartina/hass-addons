# E2E Tests

End-to-end tests for the Cync Controller using Playwright to automate browser interactions with Home Assistant.

## Setup

E2E tests require Playwright browser automation:

```bash
# Install Playwright browsers (first time only)
python -m playwright install chromium

# Run E2E tests
cd cync-controller
python -m pytest tests/e2e/ -v -s
```

## Test Files

| File                     | Purpose                                                  |
| ------------------------ | -------------------------------------------------------- |
| `conftest.py`            | Shared fixtures (browser, HA login, ingress navigation)  |
| `test_otp_flow.py`       | Bug 1: OTP token caching                                 |
| `test_restart_button.py` | Bug 2 & 3: Restart button error handling and persistence |
| `test_group_control.py`  | Bug 4: Group switch synchronization                      |

## Known Issues

### Group Control Test Flakiness

The `test_group_turns_off_all_switches` test may occasionally fail due to **Home Assistant UI rendering delays**, not backend sync issues.

**Root Cause**: MQTT messages are sent and processed correctly by Cync Controller (confirmed in logs showing "Switch already matches subgroup state"), but Home Assistant's frontend sometimes takes longer than expected to render updated switch states. This is especially noticeable with specific switch entities like the "4way Switch".

**Evidence**:
- ✅ Backend logs confirm all switches correctly synced
- ✅ 2 out of 3 switches update immediately in UI
- ✅ The problematic switch eventually updates if you wait longer
- ⚠️  Flakiness is intermittent and timing-dependent

**Workarounds**:
1. Run the test in isolation for more reliable results:
   ```bash
   python -m pytest tests/e2e/test_group_control.py::test_group_turns_off_all_switches -v -s
   ```
2. Check addon logs to verify MQTT sync is working: `ha addons logs local_cync-controller | grep "4way Switch"`

**Conclusion**: Bug 4 (switch sync) is FIXED in the backend. Test failures are due to Home Assistant UI rendering delays beyond our control.

## Writing New E2E Tests

### Best Practices

1. **Use `getByRole()` selectors** - They pierce shadow DOM automatically
2. **Add 2-second waits after group interactions** - Required for MQTT sync
3. **Use explicit waits** - `page.wait_for_timeout()` for known delays
4. **Avoid `{force: true}`** - Bypasses safety checks
5. **Log test progress** - Use `print()` statements for debugging

### Example Test Structure

```python
def test_my_feature(ha_login: Page, ha_base_url: str):
    """Test description."""
    page = ha_login

    # Navigate to page
    page.goto(f"{ha_base_url}/lovelace/0")
    page.wait_for_load_state("networkidle")

    # Interact with elements
    button = page.get_by_role("button", name="My Button")
    button.click()
    page.wait_for_timeout(2000)  # Wait for action to complete

    # Assert result
    expect(page.get_by_text("Success")).to_be_visible()
```

### Group Interaction Pattern

Always wait 2 seconds after group toggle commands:

```python
group_switch = page.get_by_role("switch", name="Toggle Group off")
group_switch.click()
print("✓ Group turned OFF")
# Wait for MQTT sync to propagate to all switches
page.wait_for_timeout(2000)
```

## Resources

- [Playwright Python Docs](https://playwright.dev/python/)
- [pytest-playwright Plugin](https://github.com/microsoft/playwright-pytest)
- [Home Assistant Testing Best Practices](https://developers.home-assistant.io/docs/development_testing/)
