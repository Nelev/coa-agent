"""C5: wrap each tool as a LangChain @tool with a Pydantic args schema.

State-injected arguments (pdf_id, previous tool outputs) are left out of the
schemas the model sees. The ToolNode returns a tool error as a message, and two
failures of the same tool end the run as REVIEW.
"""
