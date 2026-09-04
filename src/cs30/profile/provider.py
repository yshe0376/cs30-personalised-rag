"""Week 1 student profiles used by the real generation path."""

from cs30.contracts import StudentLevel, StudentProfile


class Week1ProfileProvider:
    """Create the minimum frozen profile for one of the three Week 1 levels."""

    def __init__(self, profile_prefix: str = "week1") -> None:
        prefix = profile_prefix.strip()
        if not prefix:
            raise ValueError("profile_prefix must not be empty")
        self._profile_prefix = prefix

    def get(self, level: StudentLevel) -> StudentProfile:
        if not isinstance(level, StudentLevel):
            level = StudentLevel(level)
        return StudentProfile(
            profile_id=f"{self._profile_prefix}-{level.value}",
            level=level,
            confidence=1.0,
        )
