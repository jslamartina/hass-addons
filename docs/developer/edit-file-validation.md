# Edit File Context Validation

## Overview

The `validate-edit-context.py` utility performs **byte-to-byte comparison** of context strings against actual file content to catch mismatches before `edit_file` tool calls fail.

**Note:** Always run the validator before each `edit_file` call to ensure your context matches exactly. This prevents silent failures due to whitespace or encoding mismatches.

This prevents common failures due to:

- Whitespace differences (spaces vs tabs)
- Line ending differences (LF vs CRLF)
- Encoding issues
- Context extraction errors

## Quick Start

### 1. Extract the Context You Plan to Edit

Identify the exact text (including whitespace) that you'll pass to `edit_file`:

```python
# Example: You want to replace this function
old_string = """def validate_input(data):
    if not data:
        return False
    return True"""
```

### 2. Run the Validator

```bash
cd /workspaces/hass-addons

# Validate the context exists in the file
python3 scripts/validate-edit-context.py \
  cync-controller/src/app.py \
  "def validate_input(data):"
```

### 3. Interpret the Result

**Success:**

```
✓ Context matches at line 42
```

**Failure with suggestions:**

```
✗ Context not found in file
  Searching for: "def validate_input(data):"...

  Similar lines found:
    Line 42: "def validate_input(data)  # extra spaces"
    Line 99: "def validate_Input(data):"  # wrong case

  Check for:
    - Whitespace differences (tabs vs spaces)
    - Extra/missing newlines
    - Encoding issues
    - Wrong line number
```

## CLI Usage

### Basic Validation

```bash
# Single-line context
python3 scripts/validate-edit-context.py src/app.py "def foo():"

# Multiline context (use quotes and \n)
python3 scripts/validate-edit-context.py src/app.py "def foo():\n    pass"
```

### Optional Arguments

```bash
# Specify starting line (1-indexed)
python3 scripts/validate-edit-context.py src/app.py "def foo():" --line 42

# Verbose output
python3 scripts/validate-edit-context.py src/app.py "def foo():" --verbose
```

## Programmatic Usage

### Import and Use in Python Scripts

```python
from validate_edit_context import EditContextValidator

# Create validator
validator = EditContextValidator("path/to/file.py")

# Validate context
is_valid, message = validator.validate_context("def foo():")
if is_valid:
    print(f"Valid! {message}")
else:
    print(f"Invalid: {message}")
```

### Advanced: Get Context with Surrounding Lines

```python
# Validate and show surrounding context
is_valid, message = validator.validate_with_context_lines(
    old_string="def foo():\n    pass",
    start_line=42,
    context_before=3,   # Show 3 lines before
    context_after=3     # Show 3 lines after
)
```

### Generate Detailed Diff Report

```python
# Get byte-level diff report
report = validator.byte_diff_report(
    old_string="def foo():",
    file_extraction="def foo():  "  # Extra spaces
)
print(report)
```

## Workflow Integration

### Before Each edit_file Call

**Step 1: Extract the exact context**

```python
# What you'll pass to edit_file
old_string = """def process_data(items):
    for item in items:
        handle(item)"""
```

**Step 2: Validate it exists in the file**

```bash
python3 scripts/validate-edit-context.py \
  cync-controller/src/handler.py \
  "def process_data(items):\n    for item in items:\n        handle(item)"
```

**Step 3: Make the edit_file call only if validation passes**

```python
# Now safe to call edit_file
edit_file(
    target_file="cync-controller/src/handler.py",
    instructions="I am adding error handling to the loop",
    code_edit="""def process_data(items):
    for item in items:
        try:
            handle(item)
        except Exception as e:
            logger.error(f"Failed to handle {item}: {e}")"""
)
```

## Common Issues and Solutions

### Issue: Context Not Found

**Symptom:**

```
✗ Context not found in file
```

**Diagnosis:**

1. Check for **whitespace differences**:

   ```bash
   # View the file with whitespace visible
   cat -A cync-controller/src/app.py | grep "def foo"
   ```

2. Check for **encoding issues**:

   ```bash
   # Verify file encoding
   file cync-controller/src/app.py
   ```

3. Check for **line ending differences** (LF vs CRLF):

   ```bash
   # Check for CRLF
   grep -U $'\r' cync-controller/src/app.py && echo "Has CRLF" || echo "Has LF"
   ```

4. **Verify the exact content** - Copy directly from the file:
   ```bash
   # Extract lines 42-45
   sed -n '42,45p' cync-controller/src/app.py
   ```

### Issue: Edit Fails After Validation Passes

**Cause:** File was modified between validation and edit_file call

**Solution:** Re-validate immediately before making the edit

### Issue: Tab vs Space Mismatch

**Symptom:**

```
✗ Context not found in file
Similar lines found:
  Line 42: "def foo():        " (extra spaces)
```

**Solution:** Use the exact indentation from the file. Extract with:

```bash
# Copy exact lines from file
sed -n '40,45p' cync-controller/src/app.py
```

## Test Suite

Run comprehensive tests:

```bash
python3 scripts/test-validate-edit-context.py
```

Test coverage includes:

- Exact matches
- Multiline contexts
- Tab vs space detection
- Newline handling (LF and CRLF)
- Unicode support
- Large file performance
- Similar line suggestions
- Encoding detection

## Validation Report Example

When validation fails, the validator suggests similar lines:

```
✗ Context not found in file
  Searching for: "def validate_input(data):"...

  Similar lines found:
    Line 42: def validate_input(data)  # Two spaces after
    Line 56: def validateinput(data):   # Missing underscore
    Line 78: def validate_input(data_items):  # Different parameter

  Check for:
    - Whitespace differences (tabs vs spaces)
    - Extra/missing newlines
    - Encoding issues
    - Wrong line number
```

## Performance Considerations

- **Large files (10,000+ lines):** Performs byte search in O(n) time
- **Unicode content:** Properly handles UTF-8 and mixed encodings
- **Memory usage:** Minimal - loads file once into memory

## Best Practices

1. **Always validate before edit_file calls** - Prevents silent failures
2. **Use raw strings for multiline contexts** - Easier to get exact whitespace:
   ```python
   context = r"""def foo():
       pass"""
   ```
3. **Extract directly from file** - Copy-paste to ensure accuracy
4. **Validate once, edit once** - Minimize file state changes
5. **Log the validation result** - Help with debugging
   ```python
   is_valid, msg = validator.validate_context(old_string)
   logger.info(f"Context validation: {msg}")
   ```

## Integration in Deployment Pipelines

For automated workflows:

```bash
#!/bin/bash
# Validate before making edits
python3 scripts/validate-edit-context.py "$FILE" "$CONTEXT" || {
  echo "Context validation failed"
  exit 1
}

# Safe to proceed with edit
# ... call edit_file tool ...
```

## See Also

- `edit_file` Tool Documentation
- `scripts/validate-edit-context.py` - Source code
- `scripts/test-validate-edit-context.py` - Test suite
- `development-workflow.mdc` - Full development workflow
