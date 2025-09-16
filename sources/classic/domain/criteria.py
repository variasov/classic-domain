from typing import Optional, Sequence, Generic, TypeVar, overload

from .errors import CriteriaNotSatisfied


DomainObject = TypeVar('DomainObject')


class Criteria(Generic[DomainObject]):
    """
    Базовый класс для критериев.

    Нужен для описания критериев объектов, чтобы затем определять,
    соответствуют ли те или иные объекты критерию, или для формирования запроса,
    к примеру, в SQL-хранилище.

    Взято отсюда и доработано:
    https://gist.github.com/palankai/f73a18ce06751ab8f245

    Пример:
    >>> from datetime import datetime
    ... from dataclasses import dataclass
    ... from classic.domain import Criteria
    ...
    ... @dataclass
    ... class Task:
    ...     number: int
    ...     created_at: datetime
    ...     finished_at: datetime
    ...
    ... @dataclass
    ... class TaskOlderThan(Criteria[Task]):
    ...     date: datetime
    ...
    ...     def is_satisfied_by(self, task: Task) -> bool:
    ...         return self.date < task.created_at
    ...
    ... @dataclass
    ... class TaskObsolete(Criteria[Task]):
    ...     days_to_work: int
    ...
    ...     def is_satisfied_by(self, task: Task) -> bool:
    ...         days_spent = task.finished_at - task.created_at
    ...         return days_spent.days > self.days_to_work
    ...
    ... some_task = Task(
    ...     created_at=datetime(2024, 1, 1),
    ...     finished_at=datetime(2024, 1, 10),
    ... )
    ... old_and_obsolete = (
    ...     TaskOlderThan(datetime(2024, 1, 31)) & TaskObsolete(3)
    ... )
    ... old_and_obsolete.is_satisfied_by(some_task)
    True

    >>> old_and_obsolete(some_task)
    True

    >>> list(filter(old_and_obsolete, [Task(1), Task(2), Task(3)]))
    Task(1)
    """

    def __and__(
        self, other: 'Criteria[DomainObject]',
    ) -> 'Criteria[DomainObject]':
        return And(self, other)

    def __or__(
        self, other: 'Criteria[DomainObject]',
    ) -> 'Criteria[DomainObject]':
        return Or(self, other)

    def __xor__(
        self, other: 'Criteria[DomainObject]',
    ) -> 'Criteria[DomainObject]':
        return Xor(self, other)

    def __invert__(
        self: 'Criteria[DomainObject]',
    ) -> 'Criteria[DomainObject]':
        return Invert(self)

    def is_satisfied_by(self, candidate: DomainObject) -> bool:
        raise NotImplementedError

    def __call__(self, candidate: DomainObject) -> bool:
        return self.is_satisfied_by(candidate)

    def must_be_satisfied_by(self, candidate: DomainObject) -> None:
        if not self.is_satisfied_by(candidate):
            raise CriteriaNotSatisfied

    def remainder_unsatisfied_by(
        self, candidate: DomainObject
    ) -> Optional['Criteria[DomainObject]']:
        if self.is_satisfied_by(candidate):
            return None
        else:
            return self

    @overload
    def __get__(
        self, instance: DomainObject,
        owner: type[DomainObject],
    ) -> 'BoundFormedCriteria[DomainObject]':
        ...

    @overload
    def __get__(
        self, instance: None,
        owner: type[DomainObject],
    ) -> 'Criteria[DomainObject]':
        ...

    def __get__(
        self, instance: DomainObject,
        owner: type[DomainObject],
    ):
        if instance:
            return BoundFormedCriteria(instance, self)
        else:
            return self


class BoundFormedCriteria(Generic[DomainObject]):
    instance: DomainObject
    criteria: Criteria[DomainObject]

    def __init__(
        self, instance: DomainObject,
        criteria: Criteria[DomainObject],
    ) -> None:
        self.instance = instance
        self.criteria = criteria

    def __call__(self) -> bool:
        return self.is_satisfied()

    def is_satisfied(self) -> bool:
        return self.criteria.is_satisfied_by(self.instance)

    def must_be_satisfied(self) -> None:
        self.criteria.must_be_satisfied_by(self.instance)


class CompositeCriteria(Criteria[DomainObject]):
    """
    Интерфейс критерия с неограниченным количеством вложенных критериев.

    Используется внутри библиотеки.
    """
    nested_criteria: Sequence[Criteria[DomainObject]]

    def __init__(self, *criteria: Criteria[DomainObject]):
        self.nested_criteria = list(criteria)

    def is_satisfied_by(self, candidate: DomainObject) -> bool:
        raise NotImplementedError


class And(CompositeCriteria[DomainObject]):
    """
    Критерий, проверяющий, что все вложенные критерии удовлетворяются.

    Нужен для обработки логической операции И между несколькими критериями.
    В норме используется только под капотом и вручную не инстанцируется.
    """

    def __and__(self, other: Criteria[DomainObject]) -> Criteria[DomainObject]:
        if isinstance(other, And):
            self.nested_criteria += other.nested_criteria
        else:
            self.nested_criteria += (other,)
        return self

    def is_satisfied_by(self, candidate: DomainObject) -> bool:
        return all([
            criteria.is_satisfied_by(candidate)
            for criteria in self.nested_criteria
        ])

    def remainder_unsatisfied_by(
        self, candidate: DomainObject,
    ) -> Criteria[DomainObject] | None:

        non_satisfied = [
            criteria
            for criteria in self.nested_criteria
            if not criteria.is_satisfied_by(candidate)
        ]
        if not non_satisfied:
            return None
        if len(non_satisfied) == 1:
            return non_satisfied[0]
        if len(non_satisfied) == len(self.nested_criteria):
            return self
        return And(*non_satisfied)


class Or(CompositeCriteria[DomainObject]):
    """
    Критерий, проверяющий, что хотя бы один вложенный критерий удовлетворяются.

    Нужен для обработки логической операции ИЛИ между несколькими критериями.
    В норме используется только под капотом и вручную не инстанцируется.
    """

    def __or__(self, other: Criteria[DomainObject]) -> Criteria[DomainObject]:
        if isinstance(other, Or):
            self.nested_criteria += other.nested_criteria
        else:
            self.nested_criteria += (other,)
        return self

    def is_satisfied_by(self, candidate: DomainObject) -> bool:
        return any([
            criteria.is_satisfied_by(candidate)
            for criteria in self.nested_criteria
        ])


class UnaryCriteria(Criteria[DomainObject]):
    """
    Интерфейс критерия с одним вложенным критерием.

    Используется внутри библиотеки.
    """
    nested_criteria: Criteria[DomainObject]

    def __init__(self, criteria: Criteria[DomainObject]) -> None:
        self.nested_criteria = criteria


class Invert(UnaryCriteria[DomainObject]):
    """
    Критерий, проверяющий, что вложенный критерии не удовлетворяется.

    Нужен для обработки логической операции НЕ над вложенным критериями.
    В норме используется только под капотом и вручную не инстанцируется.
    """

    def is_satisfied_by(self, candidate: DomainObject) -> bool:
        return not self.nested_criteria.is_satisfied_by(candidate)


class BinaryCriteria(Criteria[DomainObject]):
    """
    Интерфейс критерия с двумя вложенными критериями.
    Нужен для реализации операций, в которых порядок элементов имеет значение.

    Используется внутри библиотеки.
    """
    left: Criteria
    right: Criteria

    def __init__(
        self, left: Criteria[DomainObject],
        right: Criteria[DomainObject],
    ) -> None:
        self.left = left
        self.right = right

    def is_satisfied_by(self, candidate: DomainObject) -> bool:
        raise NotImplementedError


class Xor(BinaryCriteria[DomainObject]):
    """
    Критерий, проверяющий, что только один вложенный критерий удовлетворяется.

    Нужен для обработки логической операции ИСКЛЮЧАЮЩЕЕ ИЛИ
    над вложенными критериями. В норме используется
    только под капотом и вручную не инстанцируется.
    """

    def is_satisfied_by(self, candidate: DomainObject) -> bool:
        return (
            self.left.is_satisfied_by(candidate) ^
            self.right.is_satisfied_by(candidate)
        )


class ReturnsTrue(Criteria[DomainObject]):

    def is_satisfied_by(self, candidate: DomainObject) -> bool:
        return True


class ReturnsFalse(Criteria[DomainObject]):

    def is_satisfied_by(self, candidate: DomainObject) -> bool:
        return False
