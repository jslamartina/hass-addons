### 0.0.2b2
- Add restart button to export: unhidden after receiving success from submitting OTP button
- Fix cached token reading: attempted to read a binary file in text mode
- Fix device closing logic: expected exception is now `pass`ed, proper input to asyncio.wait()
- Optimizations

### 0.0.2b1
- Add "state" key and value when updating brightness, temp or RGB. Even though hass docs say it is optional, HASS logs shows exceptions when this is omitted due to using direct access to a dict key: variable_dict["key"] instead of checking for key existence or using .get().

### 0.0.2a1
- Rough in fan support (WIP)
- optimizations

## 0.0.1
- Initial release