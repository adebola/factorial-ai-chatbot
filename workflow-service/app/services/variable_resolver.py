"""
Variable resolver for workflow execution.
Handles variable interpolation and expression evaluation.
"""
import re
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from ..core.exceptions import VariableResolutionError
from ..core.logging_config import get_logger

logger = get_logger("variable_resolver")


class VariableResolver:
    """Resolves variables and expressions in workflow content"""

    # Pattern for variable interpolation {{variable_name}}
    VARIABLE_PATTERN = re.compile(r'\{\{([^}]+)\}\}')

    # Pattern for simple expressions
    EXPRESSION_PATTERN = re.compile(r'^([^=!<>]+)\s*([=!<>]+)\s*(.+)$')

    @staticmethod
    def resolve_content(content: str, variables: Dict[str, Any]) -> str:
        """
        Resolve variables in content string.

        Args:
            content: String containing {{variable}} placeholders
            variables: Dictionary of variable values

        Returns:
            Content with variables replaced
        """
        if not content:
            return content

        def replace_variable(match):
            var_path = match.group(1).strip()
            try:
                value = VariableResolver._get_nested_value(variables, var_path)
                return str(value) if value is not None else ""
            except Exception as e:
                logger.warning(f"Failed to resolve variable '{var_path}': {e}")
                return match.group(0)  # Return original if resolution fails

        return VariableResolver.VARIABLE_PATTERN.sub(replace_variable, content)

    @staticmethod
    def _get_nested_value(data: Dict[str, Any], path: str) -> Any:
        """
        Get nested value from dictionary using dot notation.

        Args:
            data: Dictionary to search
            path: Dot-separated path (e.g., "user.profile.email")

        Returns:
            Value at the specified path
        """
        keys = path.split('.')
        value = data

        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
                if value is None:
                    raise VariableResolutionError(path, f"Key '{key}' not found")
            else:
                raise VariableResolutionError(path, f"Cannot access '{key}' on non-dict value")

        return value

    @staticmethod
    def evaluate_condition(condition: str, variables: Dict[str, Any]) -> bool:
        """
        Evaluate a simple condition expression.

        Args:
            condition: Condition string (e.g., "status == 'active'")
            variables: Dictionary of variable values

        Returns:
            Boolean result of the condition
        """
        if not condition:
            return True

        try:
            # First resolve any variables in the condition
            resolved_condition = VariableResolver.resolve_content(condition, variables)

            # Parse the condition
            match = VariableResolver.EXPRESSION_PATTERN.match(resolved_condition.strip())
            if not match:
                # Try to evaluate as a simple boolean variable
                return VariableResolver._to_bool(resolved_condition.strip())

            left_operand = match.group(1).strip()
            operator = match.group(2).strip()
            right_operand = match.group(3).strip()

            # Get left value
            if left_operand in variables:
                left_value = variables[left_operand]
            else:
                left_value = VariableResolver._parse_value(left_operand)

            # Get right value
            if right_operand in variables:
                right_value = variables[right_operand]
            else:
                right_value = VariableResolver._parse_value(right_operand)

            # Evaluate based on operator
            if operator == '==':
                return left_value == right_value
            elif operator == '!=':
                return left_value != right_value
            elif operator == '<':
                return VariableResolver._compare(left_value, right_value) < 0
            elif operator == '<=':
                return VariableResolver._compare(left_value, right_value) <= 0
            elif operator == '>':
                return VariableResolver._compare(left_value, right_value) > 0
            elif operator == '>=':
                return VariableResolver._compare(left_value, right_value) >= 0
            else:
                raise VariableResolutionError(condition, f"Unknown operator: {operator}")

        except Exception as e:
            logger.error(f"Failed to evaluate condition '{condition}': {e}")
            return False

    @staticmethod
    def _parse_value(value_str: str) -> Any:
        """Parse a string value into appropriate type"""
        value_str = value_str.strip()

        # String literals (quoted)
        if (value_str.startswith('"') and value_str.endswith('"')) or \
           (value_str.startswith("'") and value_str.endswith("'")):
            return value_str[1:-1]

        # Boolean
        if value_str.lower() == 'true':
            return True
        if value_str.lower() == 'false':
            return False

        # None/null
        if value_str.lower() in ('none', 'null'):
            return None

        # Number
        try:
            if '.' in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        # Default to string
        return value_str

    @staticmethod
    def _compare(left: Any, right: Any) -> int:
        """Compare two values"""
        try:
            if left == right:
                return 0
            elif left < right:
                return -1
            else:
                return 1
        except TypeError:
            # If types don't support comparison, compare as strings
            left_str = str(left)
            right_str = str(right)
            if left_str == right_str:
                return 0
            elif left_str < right_str:
                return -1
            else:
                return 1

    @staticmethod
    def _to_bool(value: Any) -> bool:
        """Convert value to boolean"""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() not in ('', 'false', 'none', 'null', '0')
        if isinstance(value, (int, float)):
            return value != 0
        return bool(value)

    @staticmethod
    def set_variable(variables: Dict[str, Any], path: str, value: Any) -> Dict[str, Any]:
        """
        Set a variable value using dot notation.

        Args:
            variables: Dictionary of variables
            path: Dot-separated path (e.g., "user.profile.email")
            value: Value to set

        Returns:
            Updated variables dictionary
        """
        keys = path.split('.')
        current = variables

        # Navigate to the parent of the target
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            elif not isinstance(current[key], dict):
                raise VariableResolutionError(
                    path,
                    f"Cannot set nested value at '{key}' - not a dictionary"
                )
            current = current[key]

        # Set the final value
        current[keys[-1]] = value
        return variables

    @staticmethod
    def merge_variables(*variable_dicts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge multiple variable dictionaries.
        Later dictionaries override earlier ones.

        Args:
            *variable_dicts: Variable dictionaries to merge

        Returns:
            Merged dictionary
        """
        result = {}
        for var_dict in variable_dicts:
            if var_dict:
                result = VariableResolver._deep_merge(result, var_dict)
        return result

    @staticmethod
    def _deep_merge(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries"""
        result = dict1.copy()

        for key, value in dict2.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = VariableResolver._deep_merge(result[key], value)
            else:
                result[key] = value

        return result

    @staticmethod
    def add_system_variables(variables: Dict[str, Any]) -> Dict[str, Any]:
        """
        Add system variables to the context.

        Args:
            variables: Existing variables

        Returns:
            Variables with system variables added
        """
        system_vars = {
            '_system': {
                'timestamp': datetime.utcnow().isoformat(),
                'date': datetime.utcnow().strftime('%Y-%m-%d'),
                'time': datetime.utcnow().strftime('%H:%M:%S')
            }
        }

        return VariableResolver.merge_variables(variables, system_vars)

    @staticmethod
    def extract_variables_from_text(text: str, variable_name: str) -> Dict[str, Any]:
        """
        Extract and parse variables from user input text.
        Useful for extracting structured data from natural language.

        Args:
            text: User input text
            variable_name: Name for the variable to store the text

        Returns:
            Dictionary with extracted variables
        """
        variables = {variable_name: text}

        # Try to extract email
        email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        email_match = email_pattern.search(text)
        if email_match:
            variables['_extracted_email'] = email_match.group(0)

        # Try to extract phone number (simple pattern)
        phone_pattern = re.compile(r'\b\d{3}[-.]?\d{3}[-.]?\d{4}\b')
        phone_match = phone_pattern.search(text)
        if phone_match:
            variables['_extracted_phone'] = phone_match.group(0)

        # Try to extract numbers
        number_pattern = re.compile(r'\b\d+\b')
        numbers = number_pattern.findall(text)
        if numbers:
            variables['_extracted_numbers'] = numbers

        return variables