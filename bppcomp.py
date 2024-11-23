import os
import re
from typing import Dict, Set, List, Callable, Any
from dataclasses import dataclass

class CircularReferenceError(Exception):
    """Raised when a circular file reference is detected."""
    pass

@dataclass
class DirectiveMatch:
    """Represents a matched directive in the text."""
    full_match: str
    directive_name: str
    args: List[str]
    start: int
    end: int

class FileProcessor:
    def __init__(self):
        self.processed_files: Set[str] = set()
        self.current_path: List[str] = []
        self.MAX_SIZE = 60000
        self.directives: Dict[str, Callable] = {}
        
        # Register built-in directives
        self.register_directive('file', self._handle_file)
        self.register_directive('fileif', self._handle_fileif)
        self.register_directive('arg', self._handle_arg)
        self.register_directive('python_eval', self._handle_python_eval)
        self.register_directive('generate_recursive', self._handle_generate_recursive)

    def register_directive(self, name: str, handler: Callable):
        """Register a new directive handler."""
        self.directives[name] = handler

    def read_file_content(self, filename: str) -> str:
        """Read and return the contents of a file."""
        try:
            with open(filename, 'r') as file:
                content = file.read()
                return content
        except FileNotFoundError:
            print(f"Warning: File {filename} not found. Keeping original placeholder.")
            return f"[$file {filename}]"
        except Exception as e:
            print(f"Error reading file {filename}: {str(e)}")
            return f"[$file {filename}]"

    def parse_directive(self, content: str) -> DirectiveMatch | None:
        """Parse the next directive in the content."""
        pattern = r'\[\$([\w_]+)((?:\s+(?:\{.*?\}|[^\]\s]+))*)\]'
        match = re.search(pattern, content)
        
        if not match:
            return None
            
        directive_name = match.group(1)
        args_str = match.group(2).strip()
        
        # Parse arguments, handling both JSON-style and space-separated
        args = []
        if args_str:
            current_arg = ''
            in_braces = False
            
            for char in args_str:
                if char == '{':
                    in_braces = True
                    current_arg += char
                elif char == '}':
                    in_braces = False
                    current_arg += char
                elif char.isspace() and not in_braces:
                    if current_arg:
                        args.append(current_arg)
                        current_arg = ''
                else:
                    current_arg += char
                    
            if current_arg:
                args.append(current_arg)
        
        return DirectiveMatch(
            full_match=match.group(0),
            directive_name=directive_name,
            args=args,
            start=match.start(),
            end=match.end()
        )

    def _handle_generate_recursive(self, args: List[str], context: Dict[str, Any]) -> str:
        """Handle recursive pattern generation based on level."""
        if len(args) < 3:
            return "[$generate_recursive missing_arguments]"
            
        try:
            level = int(context.get('args', {}).get(args[0], '0'))
            pattern_type = args[1]
            var_name = args[2]
            operation = args[3]
            
            if pattern_type == "math":
                result = self._generate_repeated_math_pattern(level, var_name, operation)
            else:
                return f"[$generate_recursive unknown_pattern_type {pattern_type}]"
                
            return result
        except Exception as e:
            print(f"Error generating recursive pattern: {str(e)}")
            return f"[$generate_recursive {' '.join(args)}]"

    def _generate_repeated_math_pattern(self, level: int, var_name: str, operation: str) -> str:
        """Generate nested math pattern up to specified level."""
        if level == 0:
            return f"[VAR {var_name}0]"
            
        def build_pattern(n: int) -> str:
            if n == 0:
                return f"[VAR {var_name}0]"
            return f"[MATH [VAR {var_name}{n}] {operation} {build_pattern(n-1)}]"
            
        return build_pattern(level)

    def _handle_file(self, args: List[str], context: Dict[str, Any]) -> str:
        """Handle file inclusion directive."""
        if not args:
            return "[$file missing_filename]"
            
        filename = args[0]
        file_args = None
        
        # If there's a second argument, treat it as a JSON dictionary of arguments
        if len(args) > 1:
            try:
                file_args = eval(args[1])
                if not isinstance(file_args, dict):
                    print(f"Warning: Arguments for {filename} must be a dictionary")
                    file_args = None
            except Exception as e:
                print(f"Warning: Failed to parse arguments for {filename}: {str(e)}")
        
        try:
            return self.process_file_recursive(filename, file_args, context.get('depth', 0))
        except (CircularReferenceError, RecursionError) as e:
            print(f"Error processing {filename}: {str(e)}")
            return f"[# $file {filename}: infinite loop]"

    def _handle_fileif(self, args: List[str], context: Dict[str, Any]) -> str:
        """Handle file inclusion directive."""
        if not args:
            return "[# $file missing_filename]"
            
        filename = args[0]
        check = args[1]
        file_args = None
        
        print(check, context.get('args', {}), context.get('args', {}).get(check, False))
        
        if not context.get('args', {}).get(check, False):
            return ""
        
        # If there's a third argument, treat it as a JSON dictionary of arguments
        if len(args) > 2:
            try:
                file_args = eval(args[2])
                if not isinstance(file_args, dict):
                    print(f"Warning: Arguments for {filename} must be a dictionary")
                    file_args = None
            except Exception as e:
                print(f"Warning: Failed to parse arguments for {filename}: {str(e)}")
        
        try:
            return self.process_file_recursive(filename, file_args, context.get('depth', 0))
        except (CircularReferenceError, RecursionError) as e:
            print(f"Error processing {filename}: {str(e)}")
            return f"[# $file {filename}]"

    def _handle_arg(self, args: List[str], context: Dict[str, Any]) -> str:
        """Handle argument replacement directive."""
        if not args:
            return "[# $arg missing_name]"
        
        arg_name = args[0]
        return context.get('args', {}).get(arg_name, f"[# $arg {arg_name}]")

    def _handle_python_eval(self, args: List[str], context: Dict[str, Any]) -> str:
        """Handle Python evaluation directive."""
        if not args:
            return "[# $python_eval missing_expression]"
        
        expression = ' '.join(args)
        try:
            result = eval(expression)
            return str(result)
        except Exception as e:
            print(f"Error evaluating Python expression: {str(e)}")
            return f"[# $python_eval {expression}]"

    def process_file_recursive(self, filename: str, args: Dict[str, str] = None, depth: int = 0) -> str:
        """Process file inclusions recursively with cycle detection."""
        if depth > 100:  # Prevent excessive recursion
            raise RecursionError("Maximum recursion depth exceeded")
            
        if filename in self.current_path:
            raise CircularReferenceError(
                f"Circular reference detected: {' -> '.join(self.current_path + [filename])}"
            )
            
        self.current_path.append(filename)
        content = self.read_file_content(filename)
        
        # Process all directives
        context = {
            'depth': depth + 1,
            'args': args or {},
            'filename': filename
        }
        
        while True:
            directive_match = self.parse_directive(content)
            if not directive_match:
                break
                
            handler = self.directives.get(directive_match.directive_name)
            if handler:
                replacement = handler(directive_match.args, context)
            else:
                print(f"Warning: Unknown directive '{directive_match.directive_name}'")
                replacement = directive_match.full_match
            
            content = (
                content[:directive_match.start] +
                replacement +
                content[directive_match.end:]
            )
        
        self.current_path.pop()
        return content

    def process_file(self, input_filename: str, output_filename: str, initial_args: Dict[str, str] = None):
        """Process the input file and write the result to the output file."""
        try:
            processed_content = self.process_file_recursive(input_filename, initial_args)
            
            with open(output_filename, 'w') as file:
                file.write(processed_content)
            print(f"Successfully processed {input_filename} to {output_filename} in {len(processed_content)} characters")
            
        except Exception as e:
            print(f"Error processing file: {str(e)}")
            # In case of error, copy input to output
            with open(input_filename, 'r') as infile, open(output_filename, 'w') as outfile:
                outfile.write(infile.read())
            print(f"Copied original file to {output_filename} due to error")
            
# this part is just the wrapper            

import argparse

def main():
    parser = argparse.ArgumentParser(prog="bppcomp", description='Process b++ files with configurable arguments.')
    
    # Required arguments
    parser.add_argument('input_file', help='Input file to process')
    parser.add_argument('output_file', help='Output file path')
    
    # Optional argument for arbitrary key-value pairs
    parser.add_argument('-D', '--define', action='append', nargs=2,
                      metavar=('KEY', 'VALUE'),
                      help='Define arbitrary top-level arguments as key-value pairs')

    args = parser.parse_args()

    # Start with the fixed preprocessor version
    initial_args = {
        "_preproc_version": "2024.11.23.1",
        "_bppcomp": 1
    }

    # Add user-defined arguments
    if args.define:
        for key, value in args.define:
            initial_args[key] = value

    print(initial_args)
    
    processor = FileProcessor()
    processor.process_file(args.input_file, args.output_file, initial_args)

if __name__ == "__main__":
    main()
