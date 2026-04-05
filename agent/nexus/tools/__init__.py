"""CoComputer agent tools — computer control primitives for ADK."""

from nexus.tools.computer import (
    move_mouse,
    left_click,
    right_click,
    double_click,
    type_text,
    press_key,
    scroll_screen,
    drag,
)
from nexus.tools.bash import run_command
from nexus.tools.screen import take_screenshot
from nexus.tools.browser import open_browser
from nexus.tools.bg_task import request_background_task
from nexus.tools.workspace import (
    prepare_task_workspace,
    write_todo_list,
    update_todo_item,
    write_workspace_file,
    read_workspace_file,
    list_workspace_files,
)
from nexus.tools.web import web_search, scrape_web_page

ALL_TOOLS = [
    prepare_task_workspace,
    write_todo_list,
    update_todo_item,
    write_workspace_file,
    read_workspace_file,
    list_workspace_files,
    web_search,
    scrape_web_page,
    take_screenshot,
    run_command,
    move_mouse,
    left_click,
    right_click,
    double_click,
    type_text,
    press_key,
    scroll_screen,
    drag,
    open_browser,
    request_background_task,
]
