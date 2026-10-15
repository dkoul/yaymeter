import random

from api_test_agent.models import OperationModel, ParameterModel
from api_test_agent.test_design import _fill_path


def test_boundary_path_maxlength_substitution():
    op = OperationModel(
        operation_id="getItem",
        method="GET",
        path="/items/{itemId}",
        parameters=[
            ParameterModel(
                name="itemId",
                location="path",
                required=True,
                schema_type="string",
                max_length=3,
            )
        ],
    )
    rng = random.Random(42)
    long_val = "abcd"
    path = _fill_path(op.path, op, rng, {"itemId": long_val})
    assert path == f"/items/{long_val}"
