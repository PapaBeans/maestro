import os
import re
from rich.console import Console
from rich.panel import Panel
from datetime import datetime
import json
import maestro_utils
from maestro_utils import read_file
from maestro_api_router import send_progress_update
from litellm import completion
from tavily import TavilyClient

# Set environment variables for API keys for the services you are using
os.environ["OPENAI_API_KEY"] = "YOUR OPENAI API KEY"
os.environ["ANTHROPIC_API_KEY"] = "YOUR ANTHROPIC API KEY"
os.environ["GEMINI_API_KEY"] = "YOUR GEMINI API KEY"

# Define the models to be used for each stage
ORCHESTRATOR_MODEL = "gemini/gemini-1.5-flash-latest"
SUB_AGENT_MODEL = "gemini/gemini-1.5-flash-latest"
REFINER_MODEL = "gemini/gemini-1.5-flash-latest"

# Initialize the Rich Console
console = Console()

# Results/Progress colors 
color_orchestrator = "#30223c"
color_subagent = "#2b4e73"
color_refiner = "#5c3615"

def gpt_orchestrator(objective, file_content=None, previous_results=None, use_search=False):
    # Use search if and only if we receive true from submission/args
    use_search = str(use_search).lower() == 'true'
    send_progress_update(f"Calling {ORCHESTRATOR_MODEL} for your objective","Orchestrator: Calling Model",color=color_orchestrator)

    console.print(f"\n[bold]Calling Orchestrator for your objective[/bold]")

    previous_results_text = "\n".join(previous_results) if previous_results else "None"
    if file_content:
        console.print(Panel(f"File content:\n{file_content}", title="[bold blue]File Content[/bold blue]", title_align="left", border_style="blue"))
        send_progress_update(f"File content:\n{file_content}","Orchestrator: File Content", color="blue")

    messages = [
        {"role": "system", "content": "You are a detailed and meticulous assistant. Your primary goal is to break down complex objectives into manageable sub-tasks, provide thorough reasoning, and ensure code correctness. Always explain your thought process step-by-step and validate any code for errors, improvements, and adherence to best practices."},
        {"role": "user", "content": f"Based on the following objective{' and file content' if file_content else ''}, and the previous sub-task results (if any), please break down the objective into the next sub-task, and create a concise and detailed prompt for a subagent so it can execute that task. IMPORTANT!!! when dealing with code tasks make sure you check the code for errors and provide fixes and support as part of the next sub-task. If you find any bugs or have suggestions for better code, please include them in the next sub-task prompt. Please assess if the objective has been fully achieved. If the previous sub-task results comprehensively address all aspects of the objective, include the phrase 'The task is complete:' at the beginning of your response. If the objective is not yet fully achieved, break it down into the next sub-task and create a concise and detailed prompt for a subagent to execute that task.:\n\nObjective: {objective}" + ('\nFile content:\n' + file_content if file_content else '') + f"\n\nPrevious sub-task results:\n{previous_results_text}"}
    ]

    if use_search:
        messages.append({"role": "user", "content": "Please also generate a JSON object containing a single 'search_query' key, which represents a question that, when asked online, would yield important information for solving the subtask. The question should be specific and targeted to elicit the most relevant and helpful resources. Format your JSON like this, with no additional text before or after:\n{\"search_query\": \"<question>\"}\n"})

    send_progress_update(f"Messages: " + json.dumps(messages, indent=4), "Orchestrator: Messages", color=color_orchestrator)
    response = completion(model=ORCHESTRATOR_MODEL, messages=messages)
    response_text = response['choices'][0]['message']['content']

    console.print(Panel(response_text, title=f"[bold green]Orchestrator[/bold green]", title_align="left", border_style="green", subtitle="Sending task to sub-agent 👇"))
    send_progress_update(response_text, "Orchestrator: Response Text", "Sending task to sub-agent", color=color_orchestrator)

    search_query = None
    if use_search:
        json_match = re.search(r'{.*}', response_text, re.DOTALL)
        if json_match:
            json_string = json_match.group()
            try:
                search_query = json.loads(json_string)["search_query"]
                console.print(Panel(f"Search Query: {search_query}", title="[bold blue]Search Query[/bold blue]", title_align="left", border_style="blue"))
                send_progress_update(f"Search Query: {search_query}", "Orchestrator: Search Query")
                response_text = response_text.replace(json_string, "").strip()
            except json.JSONDecodeError as e:
                console.print(Panel(f"Error parsing JSON: {e}", title="[bold red]JSON Parsing Error[/bold red]", title_align="left", border_style="red"))
                console.print(Panel(f"Skipping search query extraction.", title="[bold yellow]Search Query Extraction Skipped[/bold yellow]", title_align="left", border_style="yellow"))
                send_progress_update(f"Error parsing JSON: {e}", "Orchestrator: JSON Parsing Error", color="red")
                send_progress_update("Skipping search query extraction.", "Orchestrator: JSON Parsing Error", color="yellow")
        else:
            search_query = None

    return response_text, file_content, search_query

def gpt_sub_agent(prompt, search_query=None, previous_gpt_tasks=None, use_search=False, continuation=False):
    if previous_gpt_tasks is None:
        previous_gpt_tasks = []
    send_progress_update(f"Calling {SUB_AGENT_MODEL} to complete a task:", "Sub-agent: Calling Model", color=color_subagent)
    continuation_prompt = "Continuing from the previous answer, please complete the response."
    system_message = (
        "You are an expert assistant. Your goal is to execute tasks accurately, provide detailed explanations of your reasoning, "
        "and ensure the correctness and quality of any code. Always explain your thought process and validate your output thoroughly.\n\n"
        "Previous tasks:\n" + "\n".join(f"Task: {task['task']}\nResult: {task['result']}" for task in previous_gpt_tasks)
    )
    if continuation:
        prompt = continuation_prompt

    qna_response = None
    if search_query and use_search:
        tavily = TavilyClient(api_key="your-tavily-key")
        qna_response = tavily.qna_search(query=search_query)
        console.print(f"QnA response: {qna_response}", style="yellow")
        send_progress_update(f"QnA response: {qna_response}", "Sub-agent: QnA Response",color=color_subagent)

    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": prompt}
    ]

    if qna_response:
        messages.append({"role": "user", "content": f"\nSearch Results:\n{qna_response}"})

    response = completion(model=SUB_AGENT_MODEL, messages=messages)

    response_text = response['choices'][0]['message']['content']

    console.print(Panel(response_text, title="[bold blue]Sub-agent Result[/bold blue]", title_align="left", border_style="blue", subtitle="Task completed, sending result to Orchestrator 👇"))
    if len(response_text) >= 4000:  # Threshold set to 4000 as a precaution
    send_progress_update(response_text, "Sub-agent: Response Text", "Task completed, sending result to Orchestrator 👇", color=color_subagent)
        console.print("[bold yellow]Warning:[/bold yellow] Output may be truncated. Attempting to continue the response.")
        send_progress_update("Output may be truncated. Attempting to continue the response.", "Sub-agent: Generation Warning:", color="yellow")
        continuation_response_text = gpt_sub_agent(prompt, search_query, previous_gpt_tasks, use_search, continuation=True)
        response_text += continuation_response_text

    return response_text

def anthropic_refine(objective, sub_task_results, filename, project_name, continuation=False):
    console.print("\nCalling Opus to provide the refined final output for your objective:")
    send_progress_update(f"Calling {REFINER_MODEL} to provide the refined final output for your objective:", "Refiner: Calling Model", color=color_refiner)
    messages = [
        {
            "role": "user",
            "content": [
                {"text": "Objective: " + objective + "\n\nSub-task results:\n" + "\n".join(sub_task_results) + "\n\nPlease review and refine the sub-task results into a cohesive final output. Add any missing information or details as needed. When working on code projects, ONLY AND ONLY IF THE PROJECT IS CLEARLY A CODING ONE please provide the following:\n1. Project Name: Create a concise and appropriate project name that fits the project based on what it's creating. The project name should be no more than 20 characters long.\n2. Folder Structure: Provide the folder structure as a valid JSON object, where each key represents a folder or file, and nested keys represent subfolders. Use null values for files. Ensure the JSON is properly formatted without any syntax errors. Please make sure all keys are enclosed in double quotes, and ensure objects are correctly encapsulated with braces, separating items with commas as necessary.\nWrap the JSON object in <folder_structure> tags.\n3. Code Files: For each code file, include ONLY the file name NEVER EVER USE THE FILE PATH OR ANY OTHER FORMATTING YOU ONLY USE THE FOLLOWING format 'Filename: <filename>' followed by the code block enclosed in triple backticks, with the language identifier after the opening backticks, like this:\n\n```python\n<code>\n```"}
            ]
        }
    ]
    
    send_progress_update(f"Messages: " + str(messages), "Refiner: Messages", color=color_refiner)

    response = completion(model=REFINER_MODEL, messages=messages)

    response_text = response['choices'][0]['message']['content']
    console.print(Panel(response_text, title="[bold green]Final Output[/bold green]", title_align="left", border_style="green"))
    send_progress_update(response_text, "Refiner: Final Output", color=color_refiner)

    if len(response_text) >= 4000 and not continuation:  # Threshold set to 4000 as a precaution
        send_progress_update("Response from refiner has exceeded safety threshold. Output may be truncated. Attempting to continue the response.", "Refiner: Warning", color="red")
        console.print("[bold yellow]Warning:[/bold yellow] Output may be truncated. Attempting to continue the response.")
        continuation_response_text = anthropic_refine(objective, sub_task_results + [response_text], filename, project_name, continuation=True)
        response_text += "\n" + continuation_response_text

    return response_text

def run_maestro(objective, want_search=None, want_file_path=None, file_path=""):
    # Ask the user if they want to provide a file path, if there is no associated argument
    if want_file_path is None:
        provide_file = input("Do you want to provide a file path? (y/n): ").lower() == 'y'
    else:
        provide_file = want_file_path
    
    # Reset given file_path argument if it's not a valid os path
    if not os.path.exists(os.path.abspath(file_path).replace("~","")):
        file_path = None
    
    if provide_file and file_path is None:
        file_path = input("Please enter the file path: ")
        if os.path.exists(file_path):
            file_content = read_file(file_path)
        else:
            print(f"File not found: {file_path}")
            file_content = None
    else:
        file_content = None

    # Ask the user if they want to use search
    if want_search is None:
        use_search = input("Do you want to use search? (y/n): ").lower() == 'y'
    else:
        use_search = want_search

    task_exchanges = []
    gpt_tasks = []
    
    while True:
        previous_results = [result for _, result in task_exchanges]
        if not task_exchanges:
            gpt_result, file_content_for_gpt, search_query = gpt_orchestrator(objective, file_content, previous_results, use_search)
        else:
            gpt_result, _, search_query = gpt_orchestrator(objective, previous_results=previous_results, use_search=use_search)

        if "The task is complete:" in gpt_result:
            final_output = gpt_result.replace("The task is complete:", "").strip()
            break
        else:
            sub_task_prompt = gpt_result
            if file_content_for_gpt and not gpt_tasks:
                sub_task_prompt = f"{sub_task_prompt}\n\nFile content:\n{file_content_for_gpt}"
            sub_task_result = gpt_sub_agent(sub_task_prompt, search_query, gpt_tasks, use_search)
            gpt_tasks.append({"task": sub_task_prompt, "result": sub_task_result})
            task_exchanges.append((sub_task_prompt, sub_task_result))
            file_content_for_gpt = None

    # Include both orchestrator prompts and sub-agent results in sub-task results
    sub_task_results = [f"Orchestrator Prompt: {prompt}\nSub-agent Result: {result}" for prompt, result in task_exchanges]

    sanitized_objective = re.sub(r'\W+', '_', objective)
    timestamp = datetime.now().strftime("%H-%M-%S")
    
    refined_output = anthropic_refine(objective, sub_task_results, timestamp, sanitized_objective)

    ## Get the project name from the refined output, if not found use the sanitized objective
    project_name = maestro_utils.extract_project_name(refined_output, sanitized_objective)
    # Grab all code blocks and filenames from the refined output
    code_blocks_tuples = maestro_utils.extract_and_write_project_files(refined_output, project_name)
    
    max_length = 25
    truncated_objective = sanitized_objective[:max_length] if len(sanitized_objective) > max_length else sanitized_objective

    filename = f"{timestamp}_{truncated_objective}.md"

    exchange_log = f"Objective: {objective}\n\n"
    exchange_log += "=" * 40 + " Task Breakdown " + "=" * 40 + "\n\n"
    for i, (prompt, result) in enumerate(task_exchanges, start=1):
        exchange_log += f"Task {i}:\n"
        exchange_log += f"Prompt: {prompt}\n"
        exchange_log += f"Result: {result}\n\n"

    exchange_log += "=" * 40 + " Refined Final Output " + "=" * 40 + "\n\n"
    exchange_log += refined_output
    # Do everything with our codeblocks we want (filename, content)
    for content in code_blocks_tuples:
        exchange_log += "\n".join(content)
        send_progress_update(content[1],f"File Creation: {content[0]}",color="darkolivegreen")

    console.print(f"\n[bold]Refined Final output:[/bold]\n{refined_output}")
    
    send_progress_update(refined_output,"Refined Final Output", color="darkslategrey")
    with open(filename, 'w') as file:
        file.write(exchange_log)
    print(f"\nFull exchange log saved to {filename}")
    send_progress_update(f"\nFull exchange log saved to {filename}")
    return task_exchanges

def get_ui_elements():
    return [
        {'type': 'checkbox', 'label': 'Use Search?', 'id': 'want_search'},
        {'type': 'checkbox', 'label': 'Do you want to provide a file path?', 'id': 'want_file_path'},
        {'type': 'textbox', 'label': 'File Path:', 'id': 'file_path'}
    ]

def get_required_args():
    return [
        {'name': 'objective', 'type': 'str', 'default': ''},
        {'name': 'want_search', 'type': 'bool', 'default': False},
        {'name': 'want_file_path', 'type': 'bool', 'default': False},
        {'name': 'file_path', 'type': 'str', 'default': ''}
    ]

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description="Run Maestro with a given objective.")
    parser.add_argument("--objective", type=str, default='', help="The primary objective to pass to the LLM")
    parser.add_argument("--want_search", type=bool, default=None, help="Whether to use search")
    parser.add_argument("--want_file_path", type=bool, default=None, help="Whether to the file path option")
    parser.add_argument("--file_path", type=str, default='', help="The path to the file")
    
    args = parser.parse_args()
    
    # Collecting additional arguments
    additional_args = {k: v for k, v in vars(args).items() if k != 'objective'}
    
    if args.objective == '':
        objective = input("Please enter your objective: ")
    else:
        objective = args.objective
    
    result = run_maestro(objective, **additional_args)