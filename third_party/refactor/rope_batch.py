"""Compose name-based global moves with Rope's reversible ChangeStack."""

import ast


def add_parser(subparsers, common):
    parser = subparsers.add_parser(
        "move_globals",
        parents=[common],
        help="Move named top-level functions/classes as one batch.",
    )
    parser.add_argument("--source-file", "--file", dest="source_file", required=True)
    parser.add_argument("--dest-file", "--dest", dest="dest_file", required=True)
    parser.add_argument(
        "--names",
        nargs="+",
        required=True,
        help="Space-separated top-level names; nested methods are not globals.",
    )


def _definitions(source):
    kinds = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    return [node for node in ast.parse(source).body if isinstance(node, kinds)]


def _check_names(source, names, error):
    if len(set(names)) != len(names):
        raise error("Duplicate names in batch")
    definitions = [node.name for node in _definitions(source)]
    invalid = [name for name in names if definitions.count(name) != 1]
    if invalid:
        raise error(f"Expected unique top-level functions/classes: {invalid}")


def _resources(project, root, args, api):
    source = api.resolve_path(root, args.source_file)
    dest = api.resolve_path(root, args.dest_file)
    if source == dest:
        raise api.CliError("Source and destination must differ")
    if not dest.parent.is_dir():
        raise api.CliError("Destination parent must already exist")
    resource = api.get_resource(project, root, source)
    _check_names(resource.read(), args.names, api.CliError)
    destination = project.get_file(dest.relative_to(root).as_posix())
    if project.is_ignored(resource) or project.is_ignored(destination):
        raise api.CliError("Batch source and destination must not be ignored by Rope")
    return resource, destination


def _preview_stack(project, description):
    from rope.contrib.changestack import ChangeStack

    class PreviewStack(ChangeStack):
        def push(self, changes):
            changes.do()
            self.stack.append(changes)

        def pop_all(self):
            for changes in reversed(self.stack):
                changes.undo()

    return PreviewStack(project, description)


def _prepare_destination(project, stack, destination, names, error):
    from rope.base.change import CreateFile

    if not destination.exists():
        stack.push(CreateFile(destination.parent, destination.name))
    attributes = project.get_pymodule(destination).get_attributes()
    collisions = sorted(set(names) & attributes.keys())
    if collisions:
        raise error(f"Destination already binds names: {collisions}")


def _name_bearing_resources(project, source, destination, name):
    """Files Rope could rewrite for ``name``: textual mentions + source + dest.

    Rope's occurrence finder enumerates candidates textually
    (``rope.refactor.occurrences._TextualFinder``) and only then filters them by
    resolved pyname, so a file that never contains the identifier cannot yield a
    change.  Passing this set as ``MoveGlobal.get_changes(resources=...)`` keeps
    the emitted ChangeSet identical while skipping Rope's project-wide scan
    (measured on a 353-module root: 86.7s -> 0.91s).  Source and destination are
    always added: Rope emits the destination write only when the destination is
    in ``resources``, and silently drops the moved symbol otherwise.
    """

    files = []
    for resource in project.get_python_files():
        try:
            contains = name in resource.read()
        except (OSError, UnicodeError):
            contains = True  # unreadable: keep it in the conservative set
        if contains:
            files.append(resource)
    for extra in (source, destination):
        if extra not in files:
            files.append(extra)
    return files


def _move_one(project, source, destination, name, api):
    from rope.refactor.move import MoveGlobal

    node = next(node for node in _definitions(source.read()) if node.name == name)
    offset = api.resolve_symbol_offset(source.read(), node.lineno, name=name)
    resources = _name_bearing_resources(project, source, destination, name)
    return MoveGlobal(project, source, offset).get_changes(destination, resources=resources)


def action_move_globals(project, root, args, api):
    source, destination = _resources(project, root, args, api)
    stack = _preview_stack(project, f"Move globals {args.names} to {destination.path}")
    try:
        _prepare_destination(project, stack, destination, args.names, api.CliError)
        for name in args.names:
            stack.push(_move_one(project, source, destination, name, api))
    finally:
        stack.pop_all()
    return stack.merged(), stack.description
