<p align="center">
  <img src="https://github.com/bvanelli/crpy/assets/8211602/29052a7f-759d-42ad-8ff2-dad8dcb8428e">
</p>

A python script to pull images from a Docker repository without installing Docker and its daemon.

The script creates a cache directory (~/.crpy/) to store layers already downloaded.

It was based on a simpler version called [sdenel/docker-pull-push](https://github.com/sdenel/docker-pull-push), but has
since received so many changes that it does not resemble the original code anymore.

# Installation

You can install it from the official pip repository:

```bash
pip install crpy
```

If you want to live on the edge and have the latest development features, install it directly from the repo:

```bash
pip install git+https://github.com/bvanelli/crpy.git
```

# Basic CLI usage

For a preview of the options, here is the help command:

```
usage: crpy [-h] [-k] [-p PROXY]
            {pull,push,login,logout,auth,manifest,config,commands,layer,repositories,tags,delete,resolve,version}
            ...

Package that can do basic docker command like pull and push without installing
the docker virtual machine

positional arguments:
  {pull,push,login,logout,auth,manifest,config,commands,layer,repositories,tags,delete,resolve,version}
    pull                Pulls a docker image from a remove repo.
    push                Pushes a docker image from a remove repo.
    login               Logs in on a remote repo
    logout              Logs out of a remote repo
    auth                Shows authenticated repositories
    manifest            Inspects a docker registry metadata.
    config              Inspects a docker registry metadata.
    commands            Inspects a docker registry build commands. These are
                        the same as when you check individual image layers on
                        Docker hub.
    layer               Inspects a docker registry layer.
    repositories        List the repositories on the registry.
    tags                List the tags on a repository.
    delete              Deletes a tag in a remote repo.
    resolve             Dry-run a pull to discover every endpoint (registry,
                        auth, CDN) and resolve their IPs. Useful for
                        configuring firewall rules, proxy allowlists, or DNS
                        policies in restricted networks.
    version             Displays the application version.

options:
  -h, --help            show this help message and exit
  -k, --insecure        Use insecure registry. Ignores the validation of the
                        certificate (useful for development registries).
  -p PROXY, --proxy PROXY
                        Proxy for all requests. If your proxy contains
                        authentication, pass it on the request in the usual
                        format "http://user:pass@some.proxy.com"

For reporting issues visit https://github.com/bvanelli/crpy
```

One of the original intended usages was to run it CI to cache dependencies docker image (i.e. for Gitlab). In this
case, we can check if the image already exists on the remote repository:

```bash
$ crpy manifest alpine:1.2.3
Authenticated at index.docker.io/library/alpine:latest
{'errors': [{'code': 'MANIFEST_UNKNOWN', 'message': 'manifest unknown', 'detail': 'unknown tag=1.2.3'}]}
```

You are also able to download images and save them to disk:

```bash
$ crpy pull alpine:latest alpine.tar.gz
latest: Pulling from index.docker.io/library/alpine
Authenticated at index.docker.io/library/alpine:latest
Using cache for layer 9824c27679d3
9824c27679d3: Pull complete
Downloaded image from index.docker.io/library/alpine:latest
```

On can then push this image to another repository:

```bash
$ crpy push alpine.tar.gz bvanelli/test:latest
crpy push alpine.tar.gz bvanelli/test:latest
The push refers to repository
Authenticated at index.docker.io/bvanelli/test:latest
Authenticated at index.docker.io/bvanelli/test:latest
9824c27679d3: Pushed
Pushed latest: digest: sha256:3f372403810ab0506dda12549f1035804192ef02fb36040c036845f90bd6bfe2
```

Let's now list the tags available at this repository:

```bash
$ crpy tags bvanelli/test
Authenticated at index.docker.io/bvanelli/test:latest
1.0.0
latest
```

And delete one of the tags. I show this example because both tags were the same, and deleting one will delete them both,
so use this command with caution:

```bash
$ crpy delete bvanelli/test:1.0.0
crpy delete bvanelli/test:1.0.0
Authenticated at index.docker.io/bvanelli/test:1.0.0
Authenticated at index.docker.io/bvanelli/test:1.0.0
b''
$ crpy tags bvanelli/test
Authenticated at index.docker.io/bvanelli/test:latest
```

You can also discover every network endpoint that a pull would contact, without actually downloading any data. This is
useful when you need to configure firewall rules, proxy allowlists, or DNS policies in restricted networks — container
pulls often hit multiple hosts (registry, auth server, CDN) that all need to be reachable:

```bash
$ crpy resolve alpine:latest
                                 Endpoints for alpine:latest
┏━━━━━━━━━━┳━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Role     ┃ Hostname        ┃ IPs                           ┃ URL                           ┃
┡━━━━━━━━━━╇━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ registry │ index.docker.io │ 100.50.185.129,               │ https://index.docker.io/v2/li │
│          │                 │ 174.129.222.113, 3.81.188.6,  │ brary/alpine/manifests/latest │
│          │                 │ 44.208.12.140, 52.71.174.30,  │                               │
│          │                 │ 52.86.153.188, 54.147.201.31, │                               │
│          │                 │ 54.196.196.77                 │                               │
│ auth     │ auth.docker.io  │ 104.18.43.178, 172.64.144.78  │ https://auth.docker.io/token? │
│          │                 │                               │ service=registry.docker.io&sc │
│          │                 │                               │ ope=repository:library/alpine │
│          │                 │                               │ :pull                         │
│ config   │ index.docker.io │ 100.50.185.129,               │ https://index.docker.io/v2/li │
│          │                 │ 174.129.222.113, 3.81.188.6,  │ brary/alpine/blobs/sha256:a40 │
│          │                 │ 44.208.12.140, 52.71.174.30,  │ c03cbb81c59bfb0e0887ab0b18597 │
│          │                 │ 52.86.153.188, 54.147.201.31, │ 27075da7b9cc576a1cec2c771f38c │
│          │                 │ 54.196.196.77                 │ 5fb                           │
│ layer-0  │ index.docker.io │ 100.50.185.129,               │ https://index.docker.io/v2/li │
│          │                 │ 174.129.222.113, 3.81.188.6,  │ brary/alpine/blobs/sha256:589 │
│          │                 │ 44.208.12.140, 52.71.174.30,  │ 002ba0eaed121a1dbf42f6648f29e │
│          │                 │ 52.86.153.188, 54.147.201.31, │ 5be55d5c8a6ee0f8eaa0285cc21ac │
│          │                 │ 54.196.196.77                 │ 153                           │
└──────────┴─────────────────┴───────────────────────────────┴───────────────────────────────┘
```

# Why creating this package?

Essentially, I wanted to learn how docker handles docker image pushing and pulling, and I ended up also implementing
functions that docker-cli does not address like listing repositories, deleting tags, etc. If you want to understand
what is going on under the hood, take a look at
[this great article that delves over how containers are built and pushed](https://containers.gitbook.io/build-containers-the-hard-way/).

I understand that there are many other good solutions out there, I'll list them here:

- [**DXF**](https://github.com/davedoesdev/dxf) (python): module with a command line to interact with the registry. While
some functionality is the same, **DXF does not allow pulling and saving entire images, only blobs**. This means images
will not run again once pulled from the registry.
- [**docker-ls**](https://github.com/mayflower/docker-ls) (go): module with a command line to manipulate docker
registries, focusing on listing repositories and tags. Also allows removal of tags, but **does not allow pushing and
pulling**.
- [**registry-cli**](https://github.com/andrey-pohilko/registry-cli) (python): module with a command line to manipulate
docker registries. Allows removal of tags by regex, with configurable filters and a number of images to keep. but **does
not allow pushing and pulling**. Also, the codebase was written without type-hinting, which makes using it as an API a
bit more difficult.

There are also production-ready solutions:

- [**skopeo**](https://github.com/containers/skopeo) (go): vast range of supported registries and formats. It also
implements interactions with the docker daemon so that you can interact even with already pulled images. It can also
inspect repositories, manifests, and configs.
- [**crane**](https://github.com/google/go-containerregistry/tree/main/cmd/crane) (go): also vast of support of
registry interaction. Seems to also focus on the efficiency of doing operations.

I see nothing wrong with the available solutions. However, if you are looking for a code-based approach, you want to use
python, AND you want to use async code (like every other cool kid on the block), there are no real alternatives to
interact with registries. Therefore, I started this little project to fill the gap.

If you know of any other alternative tools, feel free to open an issue or directly place a merge request editing this
README.
