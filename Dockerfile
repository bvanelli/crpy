FROM python:3.13-slim-bookworm

COPY . .
# RUN python3 -m pip install build --user
# RUN python3 -m build --sdist --wheel --outdir dist/ .
RUN pip install .

ENTRYPOINT ["crpy"]
