FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y   git build-essential cmake python3 ca-certificates   && rm -rf /var/lib/apt/lists/*

WORKDIR /opt
RUN git clone https://github.com/ggml-org/llama.cpp.git

WORKDIR /opt/llama.cpp
RUN cmake -S . -B build -DLLAMA_BUILD_SERVER=ON -DCMAKE_BUILD_TYPE=Release  && cmake --build build -j

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
