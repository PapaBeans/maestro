import re
import os
from rich.panel import Panel
from rich.console import Console

console = Console()

def read_file(file_path):
    try:
        with open(file_path, 'r') as file:
            content = file.read()
        return content
    except Exception as e:
        console.print(Panel(f"Error reading file: [bold]{file_path}[/bold]\nError: {e}", title="[bold red]File Reading Error[/bold red]", title_align="left", border_style="red"))
        return None

def generate_unique_name(base_name, existing_names):
    if base_name not in existing_names:
        existing_names.add(base_name)
        return base_name

    counter = 1
    new_name = f"{base_name}_{counter}"
    while new_name in existing_names:
        counter += 1
        new_name = f"{base_name}_{counter}"

    existing_names.add(new_name)
    return new_name

def extract_project_name(input_text, backup_name="Maestro_Project"):
    """_summary_

    Args:
        input_text (str): The content that contains our potential file name.
        backup_name (str, optional): Optional backup name. Defaults to "Maestro_Project".

    Returns:
        str: Name of the project
    """
    project_name_pattern = re.compile(r'project.*:\s*(.+)', re.IGNORECASE)
    project_name_newline_pattern = re.compile(r'project.*:\s*\n\s*(.+)', re.IGNORECASE)
    
    for line in input_text.split('\n'):
        match = project_name_pattern.search(line)
        if match:
            project_name = match.group(1).strip()
            project_name = re.sub(r'[^a-zA-Z0-9]', '', project_name)  # Remove non-alphanumeric characters with underscores
            return project_name
    
    # Check for project name on the next line
    match = project_name_newline_pattern.search(input_text)
    if match:
        project_name = match.group(1).strip()
        project_name = re.sub(r'[^a-zA-Z0-9]', '', project_name)  # Remove non-alphanumeric characters with underscores
        return project_name
    
    return backup_name

def extract_and_write_project_files(input_text, project_dir_name):
    """
    Extract and write 'code' files with content based on patterns in the input text.
    
    This function processes a multi-line string to search for specific file name patterns within backticks or other markers, extracts 
    filenames (while removing non-alphanumeric characters), generates unique names if duplicates exist, and writes extracted files with content into specified directory.
    
    Parameters:
        input_text (str): Multiline string containing potential filename patterns and file contents.
        project_directory (str): Path to the directory where extracted files will be written into. 
        If not specified, defaults to the current working directory.
    
    Returns:
        code_blocks (list of tuple): List containing tuples with filename and file content for each generated unique filename found within input text.
    """
    
    lines = input_text.split('\n')
    filename = None
    file_content = []
    inside_backticks = False
    line_buffer = []
    processing = False
    code_blocks = []
    existing_filenames = set()

    filename_patterns = [
        re.compile(r'`([^`]+?\.[a-zA-Z0-9]+)`'),                  # `filename.ext`
        re.compile(r'\*\*FileName: ([^\s]+?\.[a-zA-Z0-9]+)\*\*'), # **FileName: filename.ext**
        re.compile(r'# ([^\s]+?\.[a-zA-Z0-9]+)'),                 # # filename.ext
        re.compile(r'File: ([^\s]+?\.[a-zA-Z0-9]+)'),             # File: filename.ext
        re.compile(r'\'([^\']+?\.[a-zA-Z0-9]+)\''),               # 'filename.ext'
        re.compile(r'filename:\(([^\)]+?\.[a-zA-Z0-9]+)\)'),      # filename:(filename.ext)
        re.compile(r'\b([^\s]+?\.[a-zA-Z0-9]+)\b')                # filename.ext (as a fallback)
    ]

    # Create project directory
    os.makedirs(project_dir_name, exist_ok=True)
    console.print(Panel(f"Created project directory: [bold]{project_dir_name}[/bold]", title="[bold green]Project Directory[/bold green]", title_align="left", border_style="green"))

    for i, line in enumerate(lines):
        #print(f"Processing line {i}: {line}")  # Debugging line processing
        if not processing:
            if "Refined Final Output" in line:
                processing = True
                #print("Found 'Refined Final Output' line. Starting processing.")
            continue
        
        line_buffer.append(line)
        if len(line_buffer) > 3:
            line_buffer.pop(0)

        if re.search(r'```', line):
            # Check previous 3 lines for a filename
            for buffer_line in line_buffer:
                for pattern in filename_patterns:
                    match = pattern.search(buffer_line)
                    if match:
                        filename = generate_unique_name(match.group(1), existing_filenames)
                        filename = os.path.join(project_dir_name, filename)
                        #print(f"Found potential filename: {filename} within buffer lines.")
                        break
                if filename:
                    break
            
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            if inside_backticks and filename:
                with open(filename, 'w') as f:
                    f.write('\n'.join(file_content))
                console.print(Panel(f"Created file: [bold]{filename}[/bold]", title="[bold green]File Creation[/bold green]", title_align="left", border_style="green"))
                code_blocks.append((filename, '\n'.join(file_content)))

            inside_backticks = not inside_backticks
            if inside_backticks:
                file_content = []
            else:
                filename = None
                file_content = []
            #print(f"Backticks {'opened' if inside_backticks else 'closed'} on line {i}")

        elif inside_backticks:
            file_content.append(line)
            #print(f"Added line {i} to file content.")

    # If the last file content was not written (no closing backticks)
    if inside_backticks and filename:
        with open(filename, 'w') as f:
            f.write('\n'.join(file_content))
        console.print(Panel(f"Created file: [bold]{filename}[/bold]", title="[bold green]File Creation[/bold green]", title_align="left", border_style="green"))
        code_blocks.append((filename, '\n'.join(file_content)))
    return code_blocks

#content = read_file("/home/drm/Documents/GitHub/maestro/15-39-49_create_a_snake_game_using.md")
#pname = extract_project_name(content)
#extract_and_write_project_files(content, pname)