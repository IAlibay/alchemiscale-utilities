import click
import os
import json
import pathlib
import openfe
from gufe import tokenization
from alchemiscale import AlchemiscaleClient, Scope, ScopedKey


def get_network(filename: pathlib.Path):
    """
    Read a serialized alchemical network
    """
    with open(filename, 'r') as fd:
        network_data = json.load(fd, cls=tokenization.JSON_HANDLER.decoder)

    return openfe.AlchemicalNetwork.from_dict(network_data)


@click.command
@click.option(
    '--network_filename',
    type=click.Path(dir_okay=False, file_okay=True, path_type=pathlib.Path),
    required=True,
    help="Path to the input file of smiles",
)
@click.option(
    '--org_scope',
    type=str,
    required=True,
    help='The organization scope name',
)
@click.option(
    '--scope_name_level1',
    type=str,
    required=True,
    help='The level1 transformation scope name',
)
@click.option(
    '--scope_name_level2',
    type=str,
    required=True,
    help='The level2 transformation scope name',
)
@click.option(
   '--repeats',
   type=int,
   required=True,
   help='The number of repeats per transformation',
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
    '--scopekey_output',
    type=click.Path(dir_okay=False, file_okay=True, path_type=pathlib.Path),
    required=False,
    default="scoped-key.dat",
    help="The file name for where we write the scope key",
)
def run(
    network_filename,
    org_scope,
    scope_name_level1,
    scope_name_level2,
    repeats,
    user_id, user_key,
    scopekey_output
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

    # Get the alchemical network
    alchemical_network = get_network(network_filename)
    print(alchemical_network)

    # Set the scope for the transformation
    scope = Scope(org_scope, scope_name_level1, scope_name_level2)
    print(f"Scope is set to: {scope}")

    ## Create a network and get a scope key
    #an_sk = asc.create_network(alchemical_network, scope)

    ## store the scoped key
    #with open(scopekey_output, 'w') as f:
    #    f.write(str(network_sk))

    ## action out tasks
    #for transform in network.edges:
    #    transform_sk = asc.get_scoped_key(transform, scope)
    #    tasks = asc.create_tasks(transform_sk, count=repeats)
    #    asc.action_tasks(tasks, network_sk)
    #
    #asc.get_network_status(network_sk)


if __name__ == "__main__":
    run()

