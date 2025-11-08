# Workflow Variable System Guide

## Overview

The workflow service now fully supports variable capture and routing as shown in your example JSON. This guide demonstrates how to create workflows with:

- **Workflow-level variable definitions**
- **Choice options with text, value, and next_step**
- **Automatic variable capture from user inputs and choices**
- **Conditional branching based on variable values**
- **Variable interpolation in messages and action parameters**

## Example Workflow Structure

```json
{
  "name": "Lead Qualification",
  "description": "Qualify leads and collect information",
  "trigger": {
    "type": "message",
    "conditions": ["pricing", "demo"]
  },
  "variables": {
    "company_size": "",
    "use_case": "",
    "email": "",
    "qualified": false
  },
  "steps": [
    {
      "id": "greeting",
      "type": "message",
      "content": "I'd love to help! Let me ask a few questions.",
      "next_step": "company_size"
    },
    {
      "id": "company_size",
      "type": "choice",
      "content": "What's your company size?",
      "options": [
        {
          "text": "1-10 employees",
          "value": "small",
          "next_step": "use_case"
        },
        {
          "text": "51-200 employees",
          "value": "medium",
          "next_step": "use_case"
        }
      ],
      "variable": "company_size"
    },
    {
      "id": "use_case",
      "type": "input",
      "content": "What's your primary use case?",
      "variable": "use_case",
      "next_step": "check_qualified"
    },
    {
      "id": "check_qualified",
      "type": "condition",
      "condition": "company_size != 'small'",
      "next_step": "collect_email"
    },
    {
      "id": "collect_email",
      "type": "input",
      "content": "Great! What's your email?",
      "variable": "email",
      "next_step": "send_info"
    },
    {
      "id": "send_info",
      "type": "action",
      "action": "send_email",
      "params": {
        "to": "{{email}}",
        "subject": "Pricing for {{company_size}} companies",
        "body": "Thanks for your interest in {{use_case}}!"
      }
    }
  ]
}
```

## How It Works

### 1. Variable Declaration

Define variables at the workflow level with initial values:

```json
"variables": {
  "company_size": "",
  "use_case": "",
  "email": "",
  "qualified": false
}
```

These variables are initialized when the workflow execution starts and are accessible throughout the workflow lifecycle.

### 2. Choice Steps with Value Capture

Choice steps now support rich option objects with three fields:

```json
{
  "id": "company_size",
  "type": "choice",
  "content": "What's your company size?",
  "options": [
    {
      "text": "1-10 employees",      // Display text shown to user
      "value": "small",             // Value stored in variable
      "next_step": "use_case"       // Where to go after selection
    }
  ],
  "variable": "company_size"        // Variable to store the value
}
```

**What happens:**
- User sees "1-10 employees" as the choice text
- When selected, `company_size` variable is set to `"small"`
- Workflow automatically proceeds to the `use_case` step
- The option's `next_step` takes precedence over step-level `next_step`

### 3. Input Steps with Variable Capture

Input steps capture free-form user responses:

```json
{
  "id": "use_case",
  "type": "input",
  "content": "What's your primary use case?",
  "variable": "use_case",
  "next_step": "check_qualified"
}
```

**What happens:**
- User provides text input
- Input is stored in the `use_case` variable
- Workflow proceeds to `check_qualified` step

### 4. Conditional Branching

Condition steps evaluate variable values to determine workflow path:

```json
{
  "id": "check_qualified",
  "type": "condition",
  "condition": "company_size != 'small'",
  "next_step": "collect_email"
}
```

**Supported operators:**
- `==` (equals)
- `!=` (not equals)
- `<` (less than)
- `<=` (less than or equal)
- `>` (greater than)
- `>=` (greater than or equal)

**What happens:**
- Expression `company_size != 'small'` is evaluated
- If `true`: proceeds to `collect_email`
- If `false`: workflow ends (or goes to `else_step` if defined)

### 5. Variable Interpolation

Use `{{variable_name}}` syntax to inject variable values into content:

```json
{
  "id": "send_info",
  "type": "action",
  "action": "send_email",
  "params": {
    "to": "{{email}}",
    "subject": "Pricing for {{company_size}} companies",
    "body": "Thanks for your interest in {{use_case}}!"
  }
}
```

**What happens:**
- `{{email}}` is replaced with the actual email value
- `{{company_size}}` is replaced with "small", "medium", etc.
- `{{use_case}}` is replaced with the user's input

**Supported in:**
- Message content
- Action parameters
- Any string field in the workflow

## Implementation Details

### Backend Files Modified

1. **workflow_parser.py** (Line 76)
   - Fixed validation to allow option-level `next_step` routing
   - Updated `EXAMPLE_LEAD_QUALIFICATION` with ChoiceOption objects

### Key Backend Components

**Variable Resolution** (`variable_resolver.py`):
- `resolve_content()` - Replaces `{{variable}}` placeholders
- `evaluate_condition()` - Evaluates conditional expressions
- `set_variable()` - Sets variable values (supports dot notation)
- `merge_variables()` - Merges variable dictionaries

**Execution Service** (`execution_service.py`):
- `_process_user_choice()` (Line 675) - Captures choice value and routes to option's next_step
- `_process_user_input()` (Line 666) - Captures input text into variable
- `_execute_choice_step()` (Line 563) - Handles choice presentation and routing
- `_execute_input_step()` (Line 607) - Handles input prompts
- `_execute_condition_step()` (Line 617) - Evaluates conditions
- `_execute_action_step()` (Line 636) - Executes actions with interpolated params

**State Management** (`state_manager.py`):
- `save_state()` - Persists variables in Redis and database
- `update_variables()` - Updates variable values during execution
- `get_state()` - Retrieves variables for current session

### Variable Lifecycle

1. **Initialization** (execution_service.py:79-85)
   ```python
   variables = VariableResolver.merge_variables(
       definition.variables or {},      # Workflow-level variables
       request.initial_variables or {},  # Request-provided variables
       request.context or {}            # Context variables
   )
   ```

2. **Choice Capture** (execution_service.py:675-710)
   ```python
   def _process_user_choice(self, step, user_choice, variables):
       # Store choice value in variable
       if step.variable:
           variables[step.variable] = user_choice

       # Find matching option and extract next_step
       for option in step.options:
           if option.value == user_choice or option.text == user_choice:
               if option.next_step:
                   variables['__selected_option_next_step'] = option.next_step
   ```

3. **Input Capture** (execution_service.py:666-673)
   ```python
   def _process_user_input(self, step, user_input, variables):
       if step.variable:
           extracted_vars = VariableResolver.extract_variables_from_text(
               user_input,
               step.variable
           )
           variables.update(extracted_vars)
   ```

4. **Persistence** (state_manager.py:146-194)
   ```python
   async def update_variables(self, session_id, variables, merge=True):
       # Merge new variables with existing ones
       current_state = await self.get_state(session_id)
       current_variables = current_state.get("variables", {})
       current_variables.update(variables)

       # Save to Redis and database
       await self.save_state(...)
   ```

## Testing

Run the test suite to verify functionality:

```bash
cd ~/Documents/Dropbox/ProjectsMacBook/FactorialSystems/Projects/factorialbot/dev/backend/workflow-service
python test_variable_workflow.py
```

**Test coverage:**
- ✅ Workflow parsing with ChoiceOption objects
- ✅ Workflow validation
- ✅ Choice step structure (text, value, next_step)
- ✅ Variable definitions at workflow level
- ✅ Condition evaluation with variable references
- ✅ Variable interpolation in action parameters
- ✅ Step flow and navigation

## Migration Guide

If you have existing workflows using string options, update them to use ChoiceOption objects:

**Before:**
```json
{
  "type": "choice",
  "options": ["Small", "Medium", "Large"],
  "variable": "size",
  "next_step": "next_action"
}
```

**After:**
```json
{
  "type": "choice",
  "options": [
    {"text": "Small", "value": "small", "next_step": "next_action"},
    {"text": "Medium", "value": "medium", "next_step": "next_action"},
    {"text": "Large", "value": "large", "next_action": "next_action"}
  ],
  "variable": "size"
}
```

## Benefits

✅ **Cleaner Data**: Store normalized values (`"small"`) instead of display text (`"1-10 employees"`)
✅ **Flexible Routing**: Each choice option can have its own `next_step`
✅ **Type Safety**: Variables have defined types and initial values
✅ **Reusability**: Variables accessible across all steps
✅ **Testability**: Conditions can be unit tested with known variable values
✅ **Maintainability**: Centralized variable declarations

## Next Steps

1. ✅ Variable system fully implemented and tested
2. ✅ Example workflow updated with ChoiceOption objects
3. ✅ Validation fixed to support option-level routing
4. 🔄 Consider adding:
   - Variable type validation (string, number, boolean)
   - Array/list variables for multiple selections
   - Nested object variables (already supported via dot notation)
   - Variable transformations (uppercase, lowercase, etc.)
   - Default values for missing variables

## Support

For questions or issues, contact the development team or check:
- `workflow-service/README.md` - Service overview
- `CONVERSATIONAL_WORKFLOW_PLAN.md` - Original workflow architecture
- `test_variable_workflow.py` - Test examples