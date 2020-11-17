FROM python:3.7
MAINTAINER "github.com/corvis"

ARG prana_version
ARG release_date
ARG is_beta=False

RUN apt-get update \
  && apt-get install -y bluez \
  && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["prana"]
CMD ["http-server"]

COPY dist/prana_rc-${prana_version}-py3-none-any.whl .

RUN pip install prana_rc-${prana_version}-py3-none-any.whl[server-tornado]

LABEL x.prana.version="${prana_version}" \
      x.prana.release-date="${release_date}" \
      x.prana.is-beta="${is_beta}"
