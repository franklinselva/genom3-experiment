"""Create a set of problems for the unified planning domain."""
import unified_planning as up
from unified_planning import *


class BatteryChargingProblem(object):
    def demo_facts(self):
        """Create a list of facts for the robot to check"""
        pass
    
    def demo_execution(self):
        """Execute the problem"""
        pass

    def demo_problem(self) -> Problem:
        """Create a simple battery charging application"""
        Location = UserType("Location")
        robot_at = Fluent("robot_at", BoolType(), position=Location)
        battery_charge = Fluent("battery_charge", RealType(0, 100))
        move = InstantaneousAction("move", l_from=Location, l_to=Location)
        l_from = move.parameter("l_from")
        l_to = move.parameter("l_to")
        move.add_precondition(GE(battery_charge, 10))
        move.add_precondition(Not(Equals(l_from, l_to)))
        move.add_precondition(robot_at(l_from))
        move.add_precondition(Not(robot_at(l_to)))
        move.add_effect(robot_at(l_from), False)
        move.add_effect(robot_at(l_to), True)
        move.add_effect(battery_charge, Minus(battery_charge, 10))
        l1 = Object("l1", Location)
        l2 = Object("l2", Location)
        problem = Problem("robot")
        problem.add_fluent(robot_at)
        problem.add_fluent(battery_charge)
        problem.add_action(move)
        problem.add_object(l1)
        problem.add_object(l2)
        problem.set_initial_value(robot_at(l1), True)
        problem.set_initial_value(robot_at(l2), False)
        problem.set_initial_value(battery_charge, 100)
        problem.add_goal(robot_at(l2))

        return problem
