"""SQLite storage for immutable metric snapshots and response cache."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone


SCHEMA_VERSION = 2


def agora():
    return datetime.now(timezone.utc).isoformat()


class RepositorioMetricasSQLite:
    def __init__(self, caminho):
        self.con = sqlite3.connect(caminho)
        self.con.row_factory = sqlite3.Row
        self._migrar()

    def _migrar(self):
        # DDL is transactional. A failed upgrade leaves the old database intact.
        with self.con:
            self.con.executescript('''
            create table if not exists execucao (
                snapshot_id text primary key, iniciada_em text, finalizada_em text,
                politica_versao text, modo text, estado text default 'EM_EXECUCAO',
                erro_tipo text, erro_mensagem text, input_hash text,
                plano_json text default '{}', config_json text default '{}', override_hash text default '');
            create table if not exists consulta (
                provedor text, tipo_consulta text, chave_hash text, endpoint_versao text default 'v1',
                schema_resposta_versao text default '1', politica_versao text default '1',
                resposta_json text, status text, consultada_em text, expira_em text,
                primary key(provedor,tipo_consulta,chave_hash,endpoint_versao,schema_resposta_versao,politica_versao));
            create table if not exists consulta_execucao (
                snapshot_id text, publicacao_canonica_id text, provedor text, tipo_consulta text,
                chave_hash text, consultada_em text, cache_hit integer, resultado text,
                resposta_sha256 text, cache_age_seconds integer default 0, expira_em text,
                primary key(snapshot_id,publicacao_canonica_id,provedor,tipo_consulta,chave_hash));
            create table if not exists snapshot_entrada (
                snapshot_id text, publicacao_canonica_id text, impressao_canonica text,
                dados_json text, primary key(snapshot_id,publicacao_canonica_id));
            create table if not exists identidade (snapshot_id text, publicacao_canonica_id text, provedor text, dados_json text, primary key(snapshot_id,publicacao_canonica_id,provedor));
            create table if not exists metrica_snapshot (snapshot_id text, publicacao_canonica_id text, provedor text, nome_metrica text, categoria text, dados_json text, primary key(snapshot_id,publicacao_canonica_id,provedor,nome_metrica,categoria));
            create table if not exists revisao (snapshot_id text, publicacao_canonica_id text, provedor text, dados_json text, primary key(snapshot_id,publicacao_canonica_id,provedor));
            create table if not exists override_metricas (publicacao_canonica_id text, provedor text, identificador_externo text, justificativa text, primary key(publicacao_canonica_id,provedor));
            ''')
            self._adicionar_colunas('execucao', {'estado': "text default 'EM_EXECUCAO'", 'erro_tipo': 'text', 'erro_mensagem': 'text', 'input_hash': 'text', 'plano_json': "text default '{}'", 'config_json': "text default '{}'", 'override_hash': "text default ''"})
            self._adicionar_colunas('consulta', {'endpoint_versao': "text default 'v1'", 'schema_resposta_versao': "text default '1'", 'politica_versao': "text default '1'", 'status': 'text', 'expira_em': 'text'})
            self._adicionar_colunas('consulta_execucao', {'cache_age_seconds': 'integer default 0', 'expira_em': 'text'})
            self.con.execute(f'pragma user_version={SCHEMA_VERSION}')

    def _adicionar_colunas(self, tabela, colunas):
        existentes = {x['name'] for x in self.con.execute(f'pragma table_info({tabela})')}
        for nome, definicao in colunas.items():
            if nome not in existentes:
                self.con.execute(f'alter table {tabela} add column {nome} {definicao}')

    @staticmethod
    def _hash(chave): return hashlib.sha256(str(chave).encode()).hexdigest()

    def criar_snapshot(self, politica, modo, snapshot_id=None, publicacoes=(), plano=None, config=None, override_hash=''):
        valor = snapshot_id or datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        dados = list(publicacoes)
        entrada = [{'id': p.get('publicacao_canonica_id'), 'fingerprint': p.get('impressao_canonica', '')} for p in dados]
        input_hash = self._hash(json.dumps(entrada, sort_keys=True, ensure_ascii=False))
        with self.con:
            self.con.execute('insert into execucao(snapshot_id,iniciada_em,politica_versao,modo,estado,input_hash,plano_json,config_json,override_hash) values(?,?,?,?,?,?,?,?,?)',
                (valor, agora(), politica, modo, 'EM_EXECUCAO', input_hash, json.dumps(plano or {}, ensure_ascii=False), json.dumps(config or {}, ensure_ascii=False), override_hash))
            for p in dados:
                self.con.execute('insert into snapshot_entrada values(?,?,?,?)', (valor, p['publicacao_canonica_id'], p.get('impressao_canonica', ''), json.dumps(p, ensure_ascii=False)))
        return valor

    def finalizar_snapshot(self, snapshot, estado='CONCLUIDO', erro=None):
        if estado not in {'CONCLUIDO', 'PARCIAL', 'FALHOU'}: raise ValueError('estado de snapshot inválido')
        with self.con:
            self.con.execute('update execucao set finalizada_em=?,estado=?,erro_tipo=?,erro_mensagem=? where snapshot_id=?',
                (agora(), estado, type(erro).__name__ if erro else None, str(erro) if erro else None, snapshot))

    def snapshot(self, snapshot):
        linha = self.con.execute('select * from execucao where snapshot_id=?', (snapshot,)).fetchone()
        return dict(linha) if linha else None
    def existe_snapshot(self, snapshot): return self.snapshot(snapshot) is not None
    def entradas_snapshot(self, snapshot): return [json.loads(x[0]) for x in self.con.execute('select dados_json from snapshot_entrada where snapshot_id=? order by publicacao_canonica_id', (snapshot,))]

    def obter_consulta(self, provedor, tipo, chave, endpoint_versao='v1', schema_resposta_versao='1', politica_versao='1', permitir_expirada=False, now=None):
        linha = self.con.execute('select * from consulta where provedor=? and tipo_consulta=? and chave_hash=? and endpoint_versao=? and schema_resposta_versao=? and politica_versao=?', (provedor,tipo,self._hash(chave),endpoint_versao,schema_resposta_versao,politica_versao)).fetchone()
        if not linha: return None
        momento = now or datetime.now(timezone.utc)
        expira = datetime.fromisoformat(linha['expira_em']) if linha['expira_em'] else momento
        expirado = expira <= momento
        if expirado and not permitir_expirada: return None
        resposta = json.loads(linha['resposta_json'])
        idade = max(0, int((momento - datetime.fromisoformat(linha['consultada_em'])).total_seconds()))
        resposta['_cache'] = {'expirado': expirado, 'consultada_em': linha['consultada_em'], 'expira_em': linha['expira_em'], 'age_seconds': idade}
        return resposta

    def salvar_consulta(self, provedor, tipo, chave, resposta, endpoint_versao='v1', schema_resposta_versao='1', politica_versao='1', ttl_seconds=604800, consultada_em=None):
        if resposta.get('status') in {'ERRO_TEMPORARIO','LIMITE_EXCEDIDO','CREDENCIAL_AUSENTE'}: return
        consulta = consultada_em or agora(); expira = (datetime.fromisoformat(consulta) + timedelta(seconds=ttl_seconds)).isoformat()
        with self.con:
            self.con.execute('insert or replace into consulta(provedor,tipo_consulta,chave_hash,endpoint_versao,schema_resposta_versao,politica_versao,resposta_json,status,consultada_em,expira_em) values(?,?,?,?,?,?,?,?,?,?)', (provedor,tipo,self._hash(chave),endpoint_versao,schema_resposta_versao,politica_versao,json.dumps(resposta,ensure_ascii=False),resposta.get('status'),consulta,expira))

    def registrar_consulta(self, snapshot, canonica_id, provedor, tipo, chave, cache_hit, resposta):
        meta=resposta.get('_cache', {}); consulta=meta.get('consultada_em', agora()); expira=meta.get('expira_em')
        idade=max(0, int((datetime.now(timezone.utc)-datetime.fromisoformat(consulta)).total_seconds())) if cache_hit else 0
        texto=json.dumps(resposta,ensure_ascii=False,sort_keys=True)
        with self.con:
            self.con.execute('insert or replace into consulta_execucao values(?,?,?,?,?,?,?,?,?,?,?)', (snapshot,canonica_id,provedor,tipo,self._hash(chave),consulta,int(cache_hit),resposta.get('status',''),self._hash(texto),idade,expira))

    def salvar_identidade(self, item):
        with self.con: self.con.execute('insert or replace into identidade values(?,?,?,?)', (item['snapshot_id'],item['publicacao_canonica_id'],item['provedor'],json.dumps(item,ensure_ascii=False)))
    def salvar_metricas(self, itens):
        with self.con:
            for i in itens:
                cat='|'.join((i.get('categoria',''),str(i.get('periodo_inicio','')),str(i.get('periodo_fim',''))))
                self.con.execute('insert or replace into metrica_snapshot values(?,?,?,?,?,?)', (i['snapshot_id'],i['publicacao_canonica_id'],i['provedor'],i['nome_metrica'],cat,json.dumps(i,ensure_ascii=False)))
    def salvar_revisao(self, item):
        with self.con: self.con.execute('insert or replace into revisao values(?,?,?,?)', (item.get('snapshot_id',''),item['publicacao_canonica_id'],item['provedor'],json.dumps(item,ensure_ascii=False)))
    def itens(self, tabela, snapshot): return [json.loads(x[0]) for x in self.con.execute(f'select dados_json from {tabela} where snapshot_id=?', (snapshot,))]
    def consultas(self, snapshot): return [dict(x) for x in self.con.execute('select snapshot_id,publicacao_canonica_id,provedor,tipo_consulta,chave_hash,consultada_em,cache_hit,resultado,resposta_sha256,cache_age_seconds,expira_em from consulta_execucao where snapshot_id=?', (snapshot,))]
    def close(self): self.con.close()
