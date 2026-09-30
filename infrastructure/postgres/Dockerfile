FROM postgres:16.15-alpine3.24@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea AS extension-build
USER root
RUN apk add --no-cache build-base
ADD --checksum=sha256:d076a3098010905fd60256649327809651f6288327db6413f0938305f62ea299 \
    https://codeload.github.com/pgvector/pgvector/tar.gz/8ee86c96f0fd72390f890aa8a336fda6d3ab4c6c /tmp/pgvector.tar.gz
RUN mkdir /build \
    && tar -xzf /tmp/pgvector.tar.gz --strip-components=1 -C /build \
    && cd /build \
    && make -j2 OPTFLAGS="" with_llvm=no \
    && make DESTDIR=/extension with_llvm=no install

FROM postgres:16.15-alpine3.24@sha256:721873c34ceb9f8d8fc265984940dc982404c105f19ad51be9fdc5970a6080ea
# This service starts as postgres, so the root-only privilege-switch binary is
# unnecessary. Remove its executable (and vulnerable embedded Go runtime).
RUN rm /usr/local/bin/gosu
COPY --from=extension-build /extension/ /
COPY source.json /usr/share/azaeron/pgvector-source.json
COPY --chmod=755 entrypoint.sh /usr/local/bin/azaeron-entrypoint.sh
COPY --chmod=755 00-azaeron-family.sh /docker-entrypoint-initdb.d/00-azaeron-family.sh
# The official image initializes new named volumes with these owners. Existing
# volumes must never be attached across image families; use the restore gate.
USER postgres
ENTRYPOINT ["/usr/local/bin/azaeron-entrypoint.sh"]
CMD ["postgres"]
