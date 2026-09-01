from trace_agent.cli import build_parser, choose_interface


def scripted_input(values):
    items = iter(values)

    def read(_prompt):
        value = next(items)
        if isinstance(value, BaseException):
            raise value
        return value

    return read


def test_startup_choice_selects_terminal_or_web():
    assert choose_interface(scripted_input(["1"]), lambda _: None) == "terminal"
    assert choose_interface(scripted_input(["web"]), lambda _: None) == "web"


def test_startup_choice_reprompts_and_defaults_to_terminal():
    output = []
    assert choose_interface(scripted_input(["invalid", ""]), output.append) == "terminal"
    assert any("Please enter" in line for line in output)
    assert choose_interface(scripted_input([EOFError()]), lambda _: None) == "terminal"


def test_interface_arguments_are_available_for_noninteractive_launch():
    args = build_parser().parse_args(
        ["--interface", "web", "--host", "127.0.0.1", "--port", "9000"]
    )
    assert args.interface == "web"
    assert args.port == 9000
