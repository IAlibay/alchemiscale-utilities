import click
import os
import pathlib
from alchemiscale import AlchemiscaleClient, Scope, ScopedKey



@click.command
@click.option(
    '--scoped_key',
    type=click.Path(dir_okay=False, file_okay=True, path_type=pathlib.Path),
    required=True,
    default="scoped-key.dat",
    help="Path to a serialized ScopedKey",
)
@click.option(
    '--user_id',
    type=str,
    required=False,
    default=None,
)
@click.option(
    '--user_key',
    type=str,
    required=False,
    default=None,
)
@click.option(
    '--restart',
    is_flag=True,
    help="Restart any failures",
)
def run(
    scoped_key,
    user_id,
    user_key,
    restart,
):
    # Get the alchemiscale bits
    if user_id is None:
        user_id = os.environ['ALCHEMISCALE_ID']
    if user_key is None:
        user_key = os.environ['ALCHEMISCALE_KEY']
    asc = AlchemiscaleClient(
        'https://api.alchemiscale.org',
        user_id,
        user_key
    )

    with open(scoped_key, 'r') as f:
        network_sk = f.read()

    asc.get_network_status(network_sk)

    if restart:
        err_tasks = asc.get_network_tasks(network_sk, status="error")
        print(f"Number of errored tasks found: {len(err_tasks)}")
        if len(err_tasks) > 0:
            print("Will attempt to restart tasks")
            asc.set_tasks_status(err_tasks, 'waiting')

            print("Printing new network status")
            asc.get_network_status(network_sk)
        else:
            print("No errored tasks were found, no further action")


if __name__ == "__main__":
    run()

