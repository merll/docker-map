import unittest

from dockermap.client.cli import DockerCommandLineOutput


class TestCli(unittest.TestCase):
    def setUp(self):
        self.out = DockerCommandLineOutput()

    def test_container_create_command(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', command='sh -c "echo x"'),
            'docker create image sh -c "echo x"'
        )

    def test_container_create_name(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', name='container-name'),
            'docker create --name="container-name" image'
        )

    def test_container_create_volumes(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', volumes=['a', 'b']),
            'docker create --volume="a" --volume="b" image'
        )

    def test_container_create_volumes_binds(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', volumes=['a', 'b'], binds=['ax:a:ro', 'bx:b:rw']),
            'docker create --volume="ax:a:ro" --volume="bx:b:rw" image'
        )

    def test_container_create_user(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', user=2000),
            'docker create --user="2000" image'
        )

    def test_container_create_hostname(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', hostname='the-hostname'),
            'docker create --hostname="the-hostname" image'
        )

    def test_container_create_domainname(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', domainname='the-domain'),
            'docker create --domainname="the-domain" image'
        )

    def test_container_create_stop_timeout(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', stop_timeout=10),
            'docker create --stop-timeout="10" image'
        )

    def test_container_create_stop_signal(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', stop_signal='SIGTERM'),
            'docker create --stop-signal="SIGTERM" image'
        )

    def test_container_create_net_container(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image',
                             network_mode='container:main.app',  # Should take preference over networking_config.
                             networking_config={'EndpointsConfig': {'main.app': {}}}),
            'docker create --net=container:main.app image'
        )

    def test_container_create_net_endpoint(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image',
                             networking_config={
                                 'EndpointsConfig': {
                                     'main.app': {
                                         'Aliases': ['aa', 'ab'],
                                         'Links': ['aa:ac'],
                                         'IPAMConfig': {
                                             'IPv4Address': 'x-ip4',
                                             'IPv6Address': 'x-ip6',
                                             'LinkLocalIPs': ['x-ll-ip'],
                                         }
                                     }
                                 }
                             }),
            'docker create --net=main.app --network-alias=aa --network-alias=ab --link=aa:ac '
            '--ip=x-ip4 --ip6=x-ip6 --link-local-ip=x-ll-ip image'
        )

    def test_container_create_net_disabled(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', network_disabled=True),
            'docker create --net=none image'
        )

    def test_container_create_ports_unpublished(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', ports=[8080, 8081]),
            'docker create --expose=8080 --expose=8081 image'
        )

    def test_container_create_ports_published(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image',
                             ports=[80, (88, 'udp'), 89],
                             port_bindings={
                                 '80/tcp': ['8080'],
                                 '88/udp': ['8888/udp'],
                                 89: [('x-ip4', 8989)],
                             }),
            'docker create '
            '--expose=80 '
            '--publish=8080:80/tcp '
            '--expose=88/udp '
            '--publish=8888/udp:88/udp '
            '--expose=89 '
            '--publish=x-ip4:8989:89 image'
        )

    def test_container_create_restartpolicy_always(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', restart_policy={'Name': 'always'}),
            'docker create --restart-policy=always image'
        )

    def test_container_create_restartpolicy_on_failure(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image',
                             restart_policy={'Name': 'on-failure', 'MaximumRetryCount': 3}),
            'docker create --restart-policy=on-failure:3 image'
        )

    def test_container_create_healthcheck(self):
        self.assertEqual(
            self.out.get_cmd('create_container', image='image', healthcheck={
                'test': ['CMD', 'curl', 'http://localhost/'],
                'interval': 1,
                'timeout': 2,
                'retries': 3,
                'start_period': 4,
            }),
            'docker create '
            '--healthcheck-cmd="curl http://localhost/" '
            '--healthcheck-interval=1 '
            '--healthcheck-timeout=2 '
            '--healthcheck-retries=3 '
            '--healthcheck-start-period=4 '
            'image'
        )

    def test_container_exec(self):
        self.assertEqual(
            self.out.get_cmd('exec_create', container='container', cmd='sh -c "echo x"'),
            'docker exec --detach container sh -c "echo x"'
        )

    def test_container_wait(self):
        self.assertEqual(
            self.out.get_cmd('wait', container='container'),
            'docker wait container'
        )

    def test_container_wait_with_timeout(self):
        self.assertEqual(
            self.out.get_cmd('wait', container='container', timeout=30),
            'timeout -s INT 30 docker wait container'
        )

    def test_volume_create(self):
        self.assertEqual(
            self.out.get_cmd('create_volume', name='vol', arg1='test'),
            'docker volume create --arg1="test" vol'
        )

    def test_connect_container_to_network(self):
        self.assertEqual(
            self.out.get_cmd('connect_container_to_network', net_id='net1', container='container'),
            'docker network connect net1 container'
        )

    def test_image_list(self):
        self.assertEqual(
            self.out.get_cmd('images'),
            'docker images --no-trunc',
        )

    def test_container_list(self):
        self.assertEqual(
            self.out.get_cmd('containers'),
            'docker ps '
            '--no-trunc '
            '--format="{{.ID}}||{{.Image}}||{{.CreatedAt}}||{{.Status}}||{{.Names}}||{{.Command}}||{{.Ports}}"'
        )

    def test_version(self):
        self.assertEqual(
            self.out.get_cmd('version'),
            'docker version --format="{{json .}}"'
        )
