from pathlib import Path

from jinja2 import Environment

from buildingmotif import BuildingMOTIF
from buildingmotif.bin.cli_helpers import (
    Color,
    arg,
    get_input,
    git_global_config,
    print_tree,
)
from buildingmotif.dataclasses.library import Library
from buildingmotif.dataclasses.shape_collection import find_imports


def add_commands(library):
    @library(
        arg("path", help="Path to the library directory"),
    )
    def init(args):
        """Initialize a library"""
        library_path = Path(args.path).resolve()

        template_file = (
            Path(__file__).resolve().parents[1] / "resources" / "library.template.yml"
        )

        user_name = git_global_config().get("user.name")
        user_email = git_global_config().get("user.email")
        default_user = None
        if user_name and user_email:
            default_user = f"{user_name} <{user_email}>"

        env = Environment()
        template = env.from_string(template_file.read_text())

        repeat = True

        library_arguments = {}
        while repeat:
            print(
                f"\n{Color.CYAN}This command will guide you through creating your {Color.GREEN}library.yaml{Color.CYAN} file.{Color.RESET}\n"
            )

            library_arguments["name"] = get_input(
                "Library name",
                default=library_arguments.get("name", library_path.name),
                input_type=str,
            )
            library_arguments["version"] = get_input(
                "Version",
                default=library_arguments.get("version", "0.1.0"),
                input_type=str,
            )
            library_arguments["description"] = get_input(
                "Description",
                default=library_arguments.get("description", ""),
                input_type=str,
            )
            library_arguments["author"] = get_input(
                "Author",
                default=library_arguments.get("author", default_user),
                optional=True,
                input_type=str,
            )
            library_arguments["home"] = get_input(
                "Home page URL",
                default=library_arguments.get("home", None),
                optional=True,
                input_type=str,
            )

            print(
                f"\n{Color.CYAN}Please confirm that the following information is correct:{Color.RESET}\n"
            )
            print(
                f"{Color.GREEN}Name: {Color.BLUE}{library_arguments['name']}{Color.RESET}"
            )
            print(
                f"{Color.GREEN}Version: {Color.BLUE}{library_arguments['version']}{Color.RESET}"
            )
            print(
                f"{Color.GREEN}Description: {Color.BLUE}{library_arguments['description']}{Color.RESET}"
            )
            print(
                f"{Color.GREEN}Author: {Color.BLUE}{library_arguments.get('author', '') or ''}{Color.RESET}"
            )
            print(
                f"{Color.GREEN}Home page: {Color.BLUE}{library_arguments.get('home', '') or ''}{Color.RESET}"
            )
            print("\n")
            confirm = get_input(
                "Is this information correct?", default="y", input_type=bool
            )
            repeat = not confirm
            print("\n")

        library_path.mkdir(parents=True, exist_ok=True)
        library_file = library_path / "library.yml"
        if library_file.exists():
            overwrite = get_input(
                f"Library file '{library_file}' already exists. Overwrite?",
                default="n",
                input_type=bool,
            )
            if not overwrite:
                print(f"{Color.RED}Library initialization aborted.{Color.RESET}")
                return
        library_file.write_text(template.render(library_arguments))

    @library(
        arg("path", help="Path to the library directory"),
    )
    def load(args):
        """Load a library"""
        BuildingMOTIF("sqlite:///").setup_tables()
        # library_path = Path(args.path).resolve()
        Library.load(directory=args.path)

    @library(
        arg("path", help="Path to the library directory"),
        arg("--depth", help="Depth of the audit", type=int, default=3),
    )
    def audit(args):
        """Generate an audit report of a library's dependencies"""

        print("Setting up empty BuildingMOTIF")
        BuildingMOTIF("sqlite:///").setup_tables()
        print("\nLoading Library")
        library = Library.load(
            directory=args.path, run_shacl_inference=False, infer_templates=False
        )
        print("\nResolving Imports")
        imports = find_imports(library.get_shape_collection().graph, depth=args.depth)

        def imports_to_tree(imports):
            tree = {}
            for name, ((graph, source), imp) in imports.items():
                description = Color.RED("Not Found")
                if source == "library":
                    description = Color.GREEN("Found in library")
                elif source == "shape_collection":
                    description = Color.GREEN("Found in shape collection")
                elif source == "internet":
                    description = Color.GREEN("Found on the internet")
                item = (name, f" - {description}")
                tree[item] = imports_to_tree(imp)
            return tree

        print_tree(imports_to_tree(imports))
