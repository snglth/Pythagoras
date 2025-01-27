from typing import Union, Callable, Any
import re, inspect, copy

def _name_is_used_in_source(name: str, source: Union[Callable, str]) -> bool:
    """ Check if name is used within the source.

    This is a naive implementation for now. Should be refactored later.

    Parameters
    ----------
    name: an identifier which will be searched for in the source

    source: either a function of a source code of a function.

    Returns
    ----------
    search_result: whether the source contains a direct reference to the name

    """

    assert isinstance(name, str)
    assert name.replace("_", "").isalnum() and not name[0].isdigit(), (
            "name='" + name + "', must be a valid identifier.")

    if callable(source) and hasattr(source, "__wrapped__"):
        source = inspect.unwrap(source)
    if callable(source):
        source = inspect.getsource(source)

    searh_pattern = "[^a-zA-Z0-9_]" + name + "[^a-zA-Z0-9_]"
    search_outcome = re.search(searh_pattern, source)
    search_result = bool(search_outcome)
    return search_result


def _direct_dependencies_many_funcs(all_funcs: dict[str, Callable]) -> dict[str, set[str]]:
    """ Create sets of 1-st level (direct) dependencies for all analized functions.

    Each set always contains at least one element (the dependant function itself).

    Parameters
    ----------
    all_funcs: a dictionary with keys containing function names, and values containing actual functions

    Returns
    ----------
    direct_dependencies: a dictionary with keys containing function names, and values containing sets of function names.
        Each set direct_dependencies[some_name] contains names of oll functions from the original all_funcs,
        that are directly referenced from within some_name's source code
    """

    for fn_name in all_funcs:
        assert fn_name == all_funcs[fn_name].__name__

    direct_dependencies = {}

    for fn_name in all_funcs:
        direct_dependencies[fn_name] = set()
        for candidate_f in all_funcs:
            if _name_is_used_in_source(candidate_f, all_funcs[fn_name]):
                direct_dependencies[fn_name] |= {candidate_f}

    return direct_dependencies


def _all_dependencies_one_func(the_function: str, all_funcs: dict[str, Callable]) -> set[str]:
    """ Create a set of all dependencies (both direct and indirect) for one function.

    Resulting set always contains at least one element: the_function (the dependant function itself).

    Parameters
    ----------
    all_funcs: a dictionary with keys containing function names, and values containing actual functions

    the_function: a name of a function for which we are discovering dependencies

    Returns
    ----------
    all_dependencies_set: names of all the functions from all_funcs that are directly or indirectly
        referenced from all_funcs's source code
    """

    assert isinstance(the_function, str)
    assert the_function in all_funcs
    for fn_name in all_funcs:
        assert fn_name == all_funcs[fn_name].__name__

    direct_dependencies = _direct_dependencies_many_funcs(all_funcs)

    all_dependencies_set = copy.deepcopy(direct_dependencies[the_function])

    while True:
        new_all_dependencies_set = copy.deepcopy(all_dependencies_set)
        for f_1 in all_dependencies_set:
            for f_2 in all_funcs:
                if _name_is_used_in_source(f_2, all_funcs[f_1]):
                    new_all_dependencies_set |= {f_2}

        if new_all_dependencies_set != all_dependencies_set:
            all_dependencies_set = new_all_dependencies_set
            continue
        else:
            break

    return all_dependencies_set

