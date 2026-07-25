# Use FastAPI with explicit RAG orchestration

The backend will use FastAPI and an explicit retrieve-then-generate flow rather than PydanticAI or another agent framework. V1 always performs one KB search before generation, so direct orchestration keeps evidence policy, failures, and tests visible without introducing an agent abstraction that the product does not need.
