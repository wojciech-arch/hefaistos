FROM rust:1.85-bookworm AS librespot
RUN cargo install librespot --version 0.8.0 --locked --no-default-features \
      --features "rustls-tls-webpki-roots,with-libmdns" --root /out

FROM python:3.13-slim AS runtime
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=librespot /out/bin/librespot /usr/local/bin/librespot
COPY hefaistos ./hefaistos
RUN useradd --uid 1000 --create-home hefaistos
USER hefaistos
# `serve` starts one librespot endpoint per target in config.json. The endpoints never play
# audio: sink.sh drains PCM at real-time speed so tracks don't skip.
ENTRYPOINT ["python", "-m", "hefaistos"]
CMD ["serve"]

FROM runtime AS test
USER root
RUN pip install --no-cache-dir pytest==8.3.5
COPY tests ./tests
RUN python -m pytest -q -p no:cacheprovider tests

FROM runtime
