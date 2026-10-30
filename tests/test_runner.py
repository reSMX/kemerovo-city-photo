import pytest
from run_background import exclusive_workspace


def test_only_one_background_runner_can_own_workspace(tmp_path):
    with exclusive_workspace(tmp_path):
        with pytest.raises(RuntimeError,match='already has an active'):
            with exclusive_workspace(tmp_path):
                pass
    with exclusive_workspace(tmp_path):
        pass
