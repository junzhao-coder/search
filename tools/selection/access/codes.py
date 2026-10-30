"""Exit codes, in their own module so budget/records/browser can share them
without importing the Zhihu adapter (which imports all of them)."""

EXIT_OK = 0
EXIT_EMPTY = 3
EXIT_UNSUPPORTED = 4
EXIT_RISK = 5
EXIT_BUDGET = 6
EXIT_TRANSPORT = 7
EXIT_INPUT = 8
EXIT_EXPORT = 9
EXIT_PARTIAL = 10  # records returned, but some objects were unusable
EXIT_LOGIN_TIMEOUT = 11  # window ran out of time, no signed-in evidence seen
EXIT_LOGIN_POLL_LIMIT = 12  # poll quota spent before any signed-in evidence
EXIT_LOGIN_UNKNOWN = 13  # window opened but nothing conclusive was read
