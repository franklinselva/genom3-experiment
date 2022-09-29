import sys
from collections import OrderedDict
from enum import Enum
from functools import partial
from typing import Callable, Dict, Iterable, List, Optional, Tuple, Type

from unified_planning.engines import OptimalityGuarantee
from unified_planning.model import (
    Fluent,
    InstantaneousAction,
    Object,
    Parameter,
    Problem,
)
from unified_planning.plans import ActionInstance
from unified_planning.shortcuts import (
    BoolType,
    IntType,
    OneshotPlanner,
    RealType,
    UserType,
)


class Bridge:
    """Generic bridge between application and planning domains"""

    def __init__(self) -> None:
        # Note: Map from type instead of str to recognize subclasses.
        self._types: Dict[type, UserType] = {
            bool: BoolType(),
            int: IntType(),
            float: RealType(),
        }
        self._fluents: Dict[str, Fluent] = {}
        self._fluent_functions: Dict[str, Callable[..., object]] = {}
        self._actions: Dict[str, InstantaneousAction] = {}
        self._api_actions: Dict[str, Callable[..., object]] = {}
        self._objects: Dict[str, Object] = {}
        self._api_objects: Dict[str, object] = {}

    @property
    def objects(self) -> Dict[str, Object]:
        return self._objects

    def create_types(self, api_types: Iterable[type]) -> None:
        """Create UP user types based on api_types."""
        for api_type in api_types:
            assert api_type not in self._types.keys()
            self._types[api_type] = UserType(api_type.__name__)

    def get_type(self, api_type: type) -> UserType:
        """Return UP user type corresponding to api_type or its superclasses."""
        for check_type, user_type in self._types.items():
            if issubclass(api_type, check_type):
                return user_type

        raise ValueError(f"No corresponding UserType defined for {api_type}!")

    def get_object_type(self, api_object: object) -> UserType:
        """Return UP user type corresponding to api_object's type."""
        for api_type, user_type in self._types.items():
            if isinstance(api_object, api_type):
                return user_type

        raise ValueError(f"No corresponding UserType defined for {api_object}!")

    def create_fluent(self, function: Callable[..., object]) -> Fluent:
        """
        Create UP fluent based on function, which provides the fluent's values
         in the application domain for problem initialization.
        """
        name = function.__qualname__.split(".")[-1]
        assert name not in self._fluents.keys()
        api_types = list(function.__annotations__.items())
        _, result_api_type = api_types[-1]
        self._fluents[name] = Fluent(
            name,
            self.get_type(result_api_type),
            OrderedDict(
                (parameter_name, self.get_type(api_type))
                for parameter_name, api_type in api_types[:-1]
            ),
        )
        self._fluent_functions[name] = function
        return self._fluents[name]

    def create_fluent_from_signature(
        self,
        name: str,
        api_types: Iterable[Type],
        result_api_type: Optional[Type] = None,
    ) -> Fluent:
        """
        Create UP fluent using the UP types corresponding to the api_types given.
        By default, use BoolType() for the result unless specified otherwise through result_api_type.
        """
        assert name not in self._fluents.keys()
        self._fluents[name] = Fluent(
            name,
            self.get_type(result_api_type) if result_api_type else BoolType(),
            OrderedDict(
                [
                    (api_type.__name__.lower(), self.get_type(api_type))
                    for api_type in api_types
                ]
            ),
        )
        # Note: When not providing a function for the fluent, you need to set its initial values explicitly during problem definition.
        return self._fluents[name]

    def create_action(
        self, action: Callable[..., object]
    ) -> Tuple[InstantaneousAction, List[Parameter]]:
        """
        Create UP InstantaneousAction based on the class's signature.
        Return the InstantaneousAction with its parameters for convenient definition of its
         preconditions and effects.
        """
        assert action.__name__ not in self._actions.keys()
        parameters: Dict[str, UserType] = OrderedDict()

        if isinstance(action, object):
            # Note: For class methods, the first argument is the instance.
            action_name = action.__qualname__.split(".")[-1]

            for parameter_name, api_type in action.__call__.__annotations__.items():
                parameters[parameter_name] = self.get_type(api_type)
            _action = InstantaneousAction(action_name, _parameters=parameters)
            self._actions[action_name] = _action
            self._api_actions[action_name] = action
            return _action, _action.parameters
        else:
            if "." in action.__qualname__:
                # Add defining class of action to parameters.
                namespace = sys.modules[action.__module__]
                for name in action.__qualname__.split(".")[:-1]:
                    # Note: Use "context" to resolve potential relay to Python source file.
                    namespace = (
                        namespace.__dict__["context"][name]
                        if "context" in namespace.__dict__.keys()
                        else namespace.__dict__[name]
                    )
                assert isinstance(namespace, type)
                parameters[
                    action.__qualname__.rsplit(".", maxsplit=1)[0]
                ] = self.get_type(namespace)
            # Add action's parameter types, without its return type.
            for parameter_name, api_type in list(action.__annotations__.items())[:-1]:
                parameters[parameter_name] = self.get_type(api_type)
            _action = InstantaneousAction(_action.__name__, parameters)
            self._actions[_action.__name__] = _action
            self._api_actions[_action.__name__] = _action
            return _action, _action.parameters

    def get_executable_action(self, action: ActionInstance) -> Callable[[], object]:
        """Return API callable action corresponding to the given UP action."""
        if action.action.name not in self._api_actions.keys():
            raise ValueError(f"No corresponding action defined for {action}!")

        return (
            self._api_actions[action.action.name],
            [
                self._api_objects[parameter.object().name]
                for parameter in action.actual_parameters
            ],
        )

    def create_object(self, name: str, api_object: object) -> Object:
        """Create UP object with name based on api_object."""
        assert name not in self._objects.keys()
        self._objects[name] = Object(name, self.get_object_type(api_object))
        self._api_objects[name] = api_object
        return self._objects[name]

    def create_objects(
        self, api_objects: Optional[Dict[str, object]] = None, **kwargs: object
    ) -> List[Object]:
        """Create UP objects based on api_objects and kwargs."""
        return [
            self.create_object(name, api_object)
            for name, api_object in (
                dict(api_objects, **kwargs) if api_objects else kwargs
            ).items()
        ]

    def create_enum_objects(self, enum: Type[Enum]) -> List[Object]:
        """Create UP objects based on enum."""
        return [self.create_object(member.name, member) for member in enum]

    def get_object(self, api_object: object) -> Object:
        """Return UP object corresponding to api_object if it exists, else api_object itself."""
        name = (
            getattr(api_object, "name")
            if hasattr(api_object, "name")
            else str(api_object)
        )
        return self._objects[name] if name in self._objects.keys() else api_object

    def define_problem(
        self,
        fluents: Optional[Iterable[Fluent]] = None,
        actions: Optional[Iterable[InstantaneousAction]] = None,
        objects: Optional[Iterable[Object]] = None,
    ) -> Problem:
        """Define UP problem by its (potential subsets of) fluents, actions, and objects."""
        # Note: Reset goals and initial values to reuse this problem.
        problem = Problem()
        problem.add_fluents(self._fluents.values() if fluents is None else fluents)
        problem.add_actions(self._actions.values() if actions is None else actions)
        problem.add_objects(self._objects.values() if objects is None else objects)
        return problem

    def solve(self, problem: Problem) -> Optional[List[ActionInstance]]:
        """Solve planning problem and return list of UP actions."""
        result = OneshotPlanner(
            name="aries",
            problem_kind=problem.kind,
            optimality_guarantee=OptimalityGuarantee.SOLVED_OPTIMALLY,
        ).solve(problem)
        return result.plan.actions if result.plan else None