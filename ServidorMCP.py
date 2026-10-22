from fastmcp import FastMCP
import requests
import datetime


# Configurações de Conexão com o Mango OS 
URL_MANGO = "http://100.25.194.157:8080"
TOKEN = "Seu_Token_Mango_Aqui"

XID_NIVEL = "DP_4ee96489-f9ef-4cde-9e12-150dfa21f79c"
XID_CV = "DP_5f55191b-73af-42cb-9c48-a4b0e5964e7b"
XID_SETPOINT = "DP_e1a88fd4-0052-4c94-8659-1515c2c2cf86"

headers_leitura = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json"
}

headers_escrita = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

#  Inicializando o Servidor MCP
mcp = FastMCP("PlantaIndustrialTCC")

# Ferramentas 

@mcp.tool()
def ler_sensores() -> str:
    """
    Lê os valores em tempo real da planta industrial. 
    Retorna o PV (Nível atual), a CV (Variável de Controle) e o SP (SetPoint atual).
    Use esta ferramenta para diagnosticar o estado do sistema ou para usar o SetPoint como base para cálculos matemáticos.
    """
    url_api = f"{URL_MANGO}/rest/latest/realtime"
    
    try:
        # Lê o Nível (PV)
        resp_nivel = requests.get(url_api, headers=headers_leitura, params={"xid": XID_NIVEL})
        nivel = resp_nivel.json().get("items", [{}])[0].get("value", "Erro") if resp_nivel.status_code == 200 else "Erro"
        
        # Lê a CV
        resp_cv = requests.get(url_api, headers=headers_leitura, params={"xid": XID_CV})
        cv = resp_cv.json().get("items", [{}])[0].get("value", "Erro") if resp_cv.status_code == 200 else "Erro"

        # Lê o SetPoint (SP)
        resp_sp = requests.get(url_api, headers=headers_leitura, params={"xid": XID_SETPOINT})
        sp = resp_sp.json().get("items", [{}])[0].get("value", "Erro") if resp_sp.status_code == 200 else "Erro"
        
        return f"O PV-Nível atual é {nivel}, a CV está em {cv} e o SetPoint atual da planta é {sp}."
    
    except Exception as e:
        return f"Falha ao ler os sensores da planta: {e}"



@mcp.tool()
def ler_historico_sensores(limite: int = 150) -> str:
    """
    Lê o histórico estritamente recente das últimas leituras do PV (Nível) e da CV.
    O parâmetro limite define quantas leituras serão puxadas (padrão 150).
    Use esta ferramenta para analisar a tendência das variáveis exatas deste momento.
    """
    import datetime 
    
    url_nivel = f"{URL_MANGO}/rest/latest/point-values/time-period/{XID_NIVEL}"
    url_cv = f"{URL_MANGO}/rest/latest/point-values/time-period/{XID_CV}"
    
    agora = datetime.datetime.utcnow()
    # 5 minutos de janela
    cinco_min_atras = agora - datetime.timedelta(minutes=5)
    
    # Parâmetros limpos e exatos
    parametros = {
        "from": cinco_min_atras.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "to": agora.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        "limit": limite
    }
    
    try:
        resp_nivel = requests.get(url_nivel, headers=headers_leitura, params=parametros)
        resp_cv = requests.get(url_cv, headers=headers_leitura, params=parametros)
        
        if resp_nivel.status_code == 200 and resp_cv.status_code == 200:
            json_nivel = resp_nivel.json()
            json_cv = resp_cv.json()
            
            # O seu print provou que a resposta já é uma lista direta!
            lista_nivel = json_nivel if isinstance(json_nivel, list) else []
            lista_cv = json_cv if isinstance(json_cv, list) else []
            
            # Puxa apenas a chave "value" de cada bloco
            historico_nivel = [item.get("value") for item in lista_nivel if isinstance(item, dict) and "value" in item]
            historico_cv = [item.get("value") for item in lista_cv if isinstance(item, dict) and "value" in item]
            
            # Fatiamento final para garantir o limite
            historico_nivel = historico_nivel[-limite:]
            historico_cv = historico_cv[-limite:]
            
            return (f"Histórico (da leitura mais antiga para a mais atual dos últimos instantes):\n"
                    f"PV (Nível): {historico_nivel}\n"
                    f"CV (Esforço): {historico_cv}")
        else:
            return (
                f"Erro na API do Mango OS.\n"
                f"Status PV: {resp_nivel.status_code} | Detalhe: {resp_nivel.text[:200]}\n"
                f"Status CV: {resp_cv.status_code} | Detalhe: {resp_cv.text[:200]}"
            )
            
    except Exception as e:
        return f"Falha de comunicação com a API ao tentar ler o histórico: {e}"



#====Caso Queira dar autonomia para a IA modificar o Setpoint da Planta===="
# @mcp.tool()
# def alterar_setpoint(novo_valor: float) -> str:
#     """
#     Altera o SetPoint (alvo) do controlador PID da planta industrial.
#     O novo_valor deve ser um número representando o nível desejado.
#     """
#     url_api = f"{URL_MANGO}/rest/latest/point-values/{XID_SETPOINT}"
#     payload = {
#         "dataType": "NUMERIC",
#         "value": novo_valor
#     }
    
#     try:
#         resposta = requests.put(url_api, json=payload, headers=headers_escrita)
#         if resposta.status_code in [200, 201, 202]:
#             return f"Sucesso! O SetPoint da planta foi alterado para {novo_valor} via Modbus/OpenPLC."
#         else:
#             return f"Erro ao alterar SetPoint. HTTP Status: {resposta.status_code}"
#     except Exception as e:
#         return f"Falha de comunicação ao tentar alterar o SetPoint: {e}"

# 4. Ponto de entrada do servidor
if __name__ == "__main__":
    # Inicia o servidor para escutar o aplicativo do Agente (ex: Claude)
    mcp.run()