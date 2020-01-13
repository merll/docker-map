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
        final_kwargs = _transform_create_kwargs(initial_kwargs.copy())
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
        final_kwargs = _transform_create_kwargs(initial_kwargs.copy())
        self.assertIn(
            '--volume="/var/lib/site/config/app1:/var/lib/app/config:ro"',
            final_kwargs
        )

    def test_port(self):
        initial_kwargs = {
            'host_config': HostConfig(
                version='1.25',
                port_bindings={80: 8080},
            )
        }
        final_kwargs = _transform_create_kwargs(initial_kwargs.copy())
        self.assertIn(
            '--publish=8080:80/tcp',
            final_kwargs
        )

