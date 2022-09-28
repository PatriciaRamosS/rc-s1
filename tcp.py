# talvez o problema seja em tratar o \r\n, precisamos checar isso
import asyncio
from tcputils import *
from os import urandom
from math import ceil
from collections import deque
import time

class Servidor:
    def __init__(self, rede, porta):
        self.rede = rede
        self.porta = porta
        self.conexoes = {}
        self.callback = None
        self.rede.registrar_recebedor(self._rdt_rcv)

    def registrar_monitor_de_conexoes_aceitas(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que uma nova conexão for aceita
        """
        self.callback = callback

    def _rdt_rcv(self, src_addr, dst_addr, segment):
        src_port, dst_port, seq_no, ack_no, \
            flags, window_size, checksum, urg_ptr = read_header(segment)

        if dst_port != self.porta:
            # Ignora segmentos que não são destinados à porta do nosso servidor
            return
        if not self.rede.ignore_checksum and calc_checksum(segment, src_addr, dst_addr) != 0:
            print('descartando segmento com checksum incorreto')
            return

        payload = segment[4*(flags>>12):]
        id_conexao = (src_addr, src_port, dst_addr, dst_port)

        if (flags & FLAGS_SYN) == FLAGS_SYN:
            # A flag SYN estar setada significa que é um cliente tentando estabelecer uma conexão nova
            # TODO: talvez você precise passar mais coisas para o construtor de conexão
            conexao = self.conexoes[id_conexao] = Conexao(self, id_conexao, seq_no, ack_no, dst_port, src_port, dst_addr, src_addr)
            # TODO: você precisa fazer o handshake aceitando a conexão. Escolha se você acha melhor
            # fazer aqui mesmo ou dentro da classe Conexao.
            if self.callback:
                self.callback(conexao)
        elif id_conexao in self.conexoes:
            # Passa para a conexão adequada se ela já estiver estabelecida
            self.conexoes[id_conexao]._rdt_rcv(seq_no, ack_no, flags, payload)
            print('%s:%d -> %s:%d (porta de origem e destino)' %
                  (src_addr, src_port, dst_addr, dst_port))
        else:
            print('%s:%d -> %s:%d (pacote associado a conexão desconhecida)' %
                  (src_addr, src_port, dst_addr, dst_port))


class Conexao:
    def __init__(self, servidor, id_conexao, seq_no, ack_no, dst_port, src_port, dst_addr, src_addr):
        self.servidor = servidor
        self.id_conexao = id_conexao
        self.callback = None
        self.timer = None
        self.seq_esperado = seq_no + 1  #numero de sequencia esperado
        self.tam_segmento = ack_no #confirmação recebida
        self.fila_seg_enviado = deque() 
        self.tam_seg_enviado = 0 
        self.fila_seg_esperando = deque() 
        self.tam_janela = 1 * MSS 
        self.checado = False 
        self.SampleRTT = 1
        self.EstimatedRTT =self.SampleRTT
        self.DevRTT = self.SampleRTT/2
        self.TimeoutInterval = 1
        
        # PASSO 1:**********************************************
        # Variaveis para enviar para a conexao
        self.seq_envia = int(urandom(2).hex(), 16) 
        #Montando cabeçalho para enviar para o cliente
        segmento = make_header(
                 dst_port, src_port, self.seq_envia, self.seq_esperado, FLAGS_SYN | FLAGS_ACK)
        #Enviando resposta
        resposta = fix_checksum(segmento, src_addr, dst_addr)   
        print('%s -> %s (endereco de origem e destino)' %
        (src_addr, dst_addr))
        self.servidor.rede.enviar(resposta, src_addr)
        #print("Iniciou")
        #print("Seq_no:", seq_no)
        #********************************************************

    def _timeout(self):
        self.timer = None
        self.tam_janela /= 2
        
        if len(self.fila_seg_enviado):
            print('Esta no time')
            _, segmento, addr, tam_dados = self.fila_seg_enviado.popleft()
            self.fila_seg_enviado.appendleft((0, segmento, addr, tam_dados))
            self.servidor.rede.enviar(segmento, addr)
            self.timer = asyncio.get_event_loop().call_later(self.TimeoutInterval, self._timeout)
    
    def _rdt_rcv(self, seq_no, ack_no, flags, payload):
        # TODO: trate aqui o recebimento de segmentos provenientes da camada de rede.
        # Chame self.callback(self, dados) para passar dados para a camada de aplicação após
        # garantir que eles não sejam duplicados e que tenham sido recebidos em ordem.
        #print("Recebeu:", payload)
        
        print("Ack_no: ", ack_no)
        print("Seq_envia: ", self.seq_envia)
        #TODO: Mudei o seq_envia
        #self.seq_envia = ack_no
        # PASSO 4: Fecha conexão se recebeu flag FIN
        if (flags & FLAGS_FIN == FLAGS_FIN):
            self.tam_segmento = ack_no # atualiza o tamanho do segmento
            src_addr, src_port, dst_addr, dst_port = self.id_conexao
            
            segmento = make_header(
                dst_port, src_port, self.seq_envia, self.seq_esperado + 1, flags)
            # Inverti a ordem do src_addr com o dst_addr
            resposta = fix_checksum(segmento, src_addr, dst_addr)
            self.servidor.rede.enviar(resposta+payload, src_addr) #TODO: coloquei o payload aqui
            # Fecha conexao mandando string vazia
            self.callback(self, b'') 
            print("Entrou aqui no fim")
            return
            
        else: 
            print("NUM ESPERADO", self.seq_esperado)
            print("SEQ_NO", seq_no)
            print("Ack_no: ", ack_no)
            print("Seq_envia: ", self.seq_envia)
            if(seq_no == self.seq_esperado):
                print("Aqui seq_no == self.seq_esperado")
                self.tam_segmento = ack_no
                # verificar número de sequência esperado
                if payload != b'':
                    self.seq_esperado += len(payload)                
                    self.callback(self, payload) 
                    print("IF do payload")
                    #print("Payload: ", payload)              
                if (flags & FLAGS_ACK == FLAGS_ACK):
                    print("Flags ACK")
                    if (len(payload) > 0):
                        print("payload > 0")
                        src_addr, src_port, dst_addr, dst_port = self.id_conexao
                        print('%s -> %s (endereco de origem e destino)' %
        (src_addr, dst_addr))
                        self.seq_envia = self.tam_segmento #acrescentei isso
                        segmento = make_header(
                            dst_port, src_port, self.seq_envia, self.seq_esperado, flags)
                        resposta = fix_checksum(segmento, src_addr, dst_addr)
                        self.servidor.rede.enviar(resposta, src_addr)

                    a = self.tam_seg_enviado > 0

                    if (self.timer != None):
                        print("Esta no time")
                        self.timer.cancel()
                        self.timer = None


                        while self.tam_seg_enviado > 0:
                            print("Esta no loop do tamanho do segmento")
                            firstTime, segmento, _, len_dados = self.fila_seg_enviado.popleft()
                            self.tam_seg_enviado -= len_dados
                            
                            _, _, seq, _, _, _, _, _ = read_header(segmento)
                            

                            if seq == ack_no:
                                break

                        print("Saiu do loop")
                        if firstTime != 0:
                            self.SampleRTT = time.time() - firstTime
                            if self.checado == False:
                                self.checado = True
                                self.EstimatedRTT = self.SampleRTT
                                self.DevRTT = self.SampleRTT/2
                            else:
                                self.EstimatedRTT = (
                                    1 - 0.125) * self.EstimatedRTT + 0.125 * self.SampleRTT
                                self.DevRTT = (1 - 0.25) * self.DevRTT + 0.25 * \
                                    abs(self.SampleRTT - self.EstimatedRTT)
                            self.TimeoutInterval = self.EstimatedRTT + 4 * self.DevRTT


                    b = self.tam_seg_enviado == 0
                    if a == True and b == True:
                        self.tam_janela += MSS
                    while len(self.fila_seg_esperando):
                        resposta, src_addr, len_dados = self.fila_seg_esperando.popleft()

                        if self.tam_seg_enviado + len_dados > self.tam_janela:
                            self.fila_seg_esperando.appendleft(
                                (resposta, src_addr, len_dados))
                            break

                        self.tam_seg_enviado += len_dados
                        self.servidor.rede.enviar(resposta, src_addr)
                        self.fila_seg_enviado.append(
                            (time.time(), resposta, src_addr, len_dados))

                    if len(self.fila_seg_enviado):
                        self.timer = asyncio.get_event_loop().call_later(
                            self.TimeoutInterval, self._timeout)
                    # else:
                        # self.tam_janela += MSS
                        
        print("Esta aqui no fim do rcv")
    # Os métodos abaixo fazem parte da API

    def registrar_recebedor(self, callback):
        """
        Usado pela camada de aplicação para registrar uma função para ser chamada
        sempre que dados forem corretamente recebidos
        """
        self.callback = callback

    def enviar(self, dados):
        """
        Usado pela camada de aplicação para enviar dados
        """
        # TODO: implemente aqui o envio de dados.
        # Chame self.servidor.rede.enviar(segmento, dest_addr) para enviar o segmento
        # que você construir para a camada de rede.
        print("Foi chamado o enviar")
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        size = ceil(len(dados)/MSS)
        for i in range(size):
            self.seq_envia = self.tam_segmento
            segment = make_header(
                dst_port, src_port, self.seq_envia, self.seq_esperado, flags=FLAGS_ACK)
            segment += (dados[i*MSS:min((i+1)*MSS, len(dados))])
            len_dados = len(dados[i*MSS:min((i+1)*MSS, len(dados))])
            self.tam_segmento += len_dados
            resposta = fix_checksum(segment, src_addr, dst_addr)
            if (self.tam_seg_enviado + len_dados) <= self.tam_janela:
                #print(resposta)
                self.servidor.rede.enviar(resposta, src_addr)
                self.fila_seg_enviado.append(
                    (time.time(), resposta, src_addr, len_dados))
                self.tam_seg_enviado += len_dados  #+= len(resposta)
                if (self.timer == None):
                    self.timer = asyncio.get_event_loop().call_later(
                        self.TimeoutInterval, self._timeout)
            else:
                self.fila_seg_esperando.append((resposta, src_addr, len_dados))

    def fechar(self):
        """
        Usado pela camada de aplicação para fechar a conexão
        """
        # TODO: implemente aqui o fechamento de conexão
        print("Fechando")
        self.seq_envia = self.tam_segmento
        src_addr, src_port, dst_addr, dst_port = self.id_conexao
        segmento = make_header(
            dst_port, src_port, self.seq_envia, self.seq_esperado + 1, FLAGS_FIN)
        resposta = fix_checksum(segmento, src_addr, dst_addr)
        self.servidor.rede.enviar(resposta, src_addr)
