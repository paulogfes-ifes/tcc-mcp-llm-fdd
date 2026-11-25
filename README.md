# tcc-mcp-llm-fdd

Repositório do Trabalho de Conclusão de Curso em Engenharia de Controle e Automação (IFES), referente à integração exploratória de agentes baseados em Grandes Modelos de Linguagem (LLMs) a um sistema SCADA virtualizado via **Model Context Protocol (MCP)** para classificação sob demanda de cenários operacionais e falhas únicas em uma malha de controle de nível.

## Arquitetura e componentes

- **Planta virtual e injeção de cenários (`flows_node_red_tcc.json`):** simulação da dinâmica de tanque no Node-RED com comunicação via sockets TCP/IP e rotas HTTP para operação nominal, falha de bomba, vazamento e falha de sensor.
- **Controle lógico (`ControladorTCC.st`):** malha de controle PID em linguagem estruturada / Ladder no OpenPLC com exposição de registradores via Modbus TCP/IP.
- **Supervisão e histórico:** aquisição e registro de séries temporais no Mango Automation com disponibilização de dados via API HTTP/REST.
- **Camada MCP e orquestração (`ServidorMCP.py` e `ClientMCP.py`):** servidor MCP local em Python (expondo ferramentas de leitura instantânea e histórica) e cliente orquestrador conectado à API do OpenRouter para execução dos ensaios em teste cego, registro de métricas e rotina de *fallback*.

## Execução e segurança

As chaves de API e *tokens* de acesso não são versionados no repositório; configure as variáveis de ambiente/credenciais localmente antes de executar os scripts em Python.
