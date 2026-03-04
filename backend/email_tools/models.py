from pydantic import BaseModel, ConfigDict


class EmailHealthStatus(BaseModel):
    model_config = ConfigDict(strict=True)

    status: str
    message: str
