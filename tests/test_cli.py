from unittest import TestCase

from docker.types import HostConfig

from dockermap.client.cli import _transform_create_kwargs


class TransformCreateKwargs(TestCase):

    def test_link(self):
        initial_kwargs = {
            'host_config': HostConfig(
                version='1.25',
                links=[('from', 'to')],
            )
        }
        final_kwargs = _transform_create_kwargs(initial_kwargs)
        self.assertIn(
            '--link="from:to"',
            final_kwargs
        )

    def test_host(self):
        initial_kwargs = {
            'host_config': HostConfig(
                version='1.25',
                binds=['/var/lib/site/config/app1:/var/lib/app/config:ro'],
            )
        }
        final_kwargs = _transform_create_kwargs(initial_kwargs)
        self.assertIn(
            '--volume="/var/lib/site/config/app1:/var/lib/app/config:ro"',
            final_kwargs
        )

