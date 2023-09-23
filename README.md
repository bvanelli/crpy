<p align="center">
  <img src="https://github.com/bvanelli/crpy/assets/8211602/29052a7f-759d-42ad-8ff2-dad8dcb8428e">
</p>

A python script to pull images from a Docker repository without installing Docker and its daemon.

The script creates a cache directory (~/.crpy/) to store layers already downloaded.

It was based on a simpler version called [sdenel/docker-pull-push](https://github.com/sdenel/docker-pull-push), but has
since received so many changes that it does not resemble the original code anymore.

# Basic usage

TODO: Fill in once the "final" version of the API is stable. For a preview of the options, here is the help command:

```
>>> crpy --help
usage: crpy [-h] [-k] [-p PROXY] {pull,push,login,inspect,repositories,tags,delete} ...

Package that can do basic docker command like pull and push without installing the docker virtual machine

positional arguments:
  {pull,push,login,inspect,repositories,tags,delete}
    pull                Pulls a docker image from a remove repo.
    push                Pushes a docker image from a remove repo.
    login               Logs in on a remote repo
    inspect             Inspects a docker registry metadata. It can inspect configs, manifests and layers.
    repositories        List the repositories on the registry.
    tags                List the tags on a repository.
    delete              Deletes a tag in a remote repo.

options:
  -h, --help            show this help message and exit
  -k, --insecure        Use insecure registry. Ignores the validation of the certificate (useful for
                        development registries).
  -p PROXY, --proxy PROXY
                        Proxy for all requests.

For reporting issues visit https://github.com/bvanelli/crpy
```

# Installation

You can install it from the official pip repository:

```bash
pip install crpy
```

If you want to live on the edge and have the latest development features, install it directly from the repo:

```bash
pip install git+https://github.com/bvanelli/crpy.git
```

# Why creating this package?

Essentially, I wanted to learn how docker handles docker image pushing and pulling, and I ended up also implementing
functions that docker-cli does not address like listing repositories, deleting tags, etc. If you want to understand
what is going on under the hood, take a look at
[this great article that delves over how containers are built and pushed](https://containers.gitbook.io/build-containers-the-hard-way/).

I understand that there are many other good solutions out there, I'll list them here:

- [**DXF**](https://github.com/davedoesdev/dxf) (python): module with command line to interact with the registry. While
some functionality is the same, **DXF does not allow to pull and save entire images, only blobs**. This means images
will not run again once pulled from the registry.
- [**docker-ls**](https://github.com/mayflower/docker-ls) (go): module with command line to manipulate docker
registries, focusing on listing repositories and tags. Also allows removal of tags, but **does not allow pushing and
pulling**.
- [**registry-cli**](https://github.com/andrey-pohilko/registry-cli) (python): module with command line to manipulate
docker registries. Allows removal of tags by regex, with configurable filters and number of images to keep. but **does
not allow pushing and pulling**. Also, the codebase was written without type-hinting, which makes using it as an API a
bit more difficult.

There are also production-ready solutions:

- [**skopeo**](https://github.com/containers/skopeo) (go): very wide range of supported registries and formats. It also
implements interactions with the docker daemon, so that you can interact even with already pulled images. It can also
inspect repositories, manifests and configs.
- [**crane**](https://github.com/google/go-containerregistry/tree/main/cmd/crane) (go): also very wide of support of
registry interaction. Seems to also focus on the efficiency of doing operations.

I see nothing wrong with the available solutions, but if you are looking for a code based approach, you want to use
python AND you want to use async code (like every other cool kid on the block), there are no real alternatives to
interact with registries. Therefore, I started this little project to fill the gap.

If you know of any other alternative tools, feel free to open an issue or directly place a merge request editing this
README.
