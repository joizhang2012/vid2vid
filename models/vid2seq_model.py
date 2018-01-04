from collections import OrderedDict

import torch
import numpy as np
from torch.autograd import Variable
from models.base_model import BaseModel
import models.networks as networks
import warnings
import util.util as util


class Vid2SeqModel(BaseModel):
    """
    Generate sequence conditioned on input video data, using GAN with CNN-LSTM generator and
        multi-layer bidirectional LSTM as discriminator
    """

    def name(self):
        return 'Vid2SeqModel'

    def initialize(self, opt):
        BaseModel.initialize(self, opt)
        self.dataset_mode = opt.dataset_mode
        self.isTrain = opt.isTrain

        # define tensors
        # 3D tensor shape (N,Cin,Din,Hin,Win)
        # self.input_vid = self.Tensor(opt.batchSize, opt.input_nc,
        #                          opt.depth, opt.fineSize, opt.fineSize)
        self.input_A = self.Tensor(opt.batchSize, opt.input_nc,
                                   int(opt.depth / 2), opt.fineSize, opt.fineSize)
        self.input_B = self.Tensor(opt.batchSize, opt.output_nc,
                                   int(opt.depth / 2), opt.fineSize, opt.fineSize)
        # self.speedX = self.Tensor(opt.batchSize, opt.depth)
        self.seq_A = self.Tensor(opt.batchSize, int(opt.depth / 2))
        self.seq_B = self.Tensor(opt.batchSize, int(opt.depth / 2))

        # load/define networks
        self.netE = networks.define_encoder(opt.input_nc, opt.output_nc, opt.ngf, opt.which_model_encoder, 
                                        opt.norm, not opt.no_dropout, opt.init_type, self.gpu_ids)

        self.netG_vid = networks.define_G(opt.input_nc, opt.output_nc, opt.ngf, opt.which_model_netG_vid, 
                                        opt.norm, not opt.no_dropout, opt.init_type, self.gpu_ids)

        self.netG_seq = networks.define_G(opt.input_nc, opt.output_nc, opt.ngf, opt.which_model_netG_seq, 
                                        opt.norm, not opt.no_dropout, opt.init_type, self.gpu_ids)

        if self.isTrain:
            use_sigmoid = opt.no_lsgan
            # change sequence_dim to 2 if the sequence is 'action'
            self.netD_seq = networks.define_D(opt.input_nc + opt.output_nc, opt.ndf, opt.which_model_netD_seq,
                                              opt.n_layers_D, opt.norm, use_sigmoid, opt.init_type, self.gpu_ids, sequence_depth=opt.depth, sequence_dim=1) 
            
            # self.netD_action = networks.define_D(opt.input_nc + opt.output_nc, opt.ndf, opt.which_model_netD_seq,
            #                                   opt.n_layers_D, opt.norm, use_sigmoid, opt.init_type, self.gpu_ids, 
            #                                   sequence_dim=2, sequence_depth=opt.seq_depth)

            self.netD_vid = networks.define_D(opt.input_nc + opt.output_nc, opt.ndf,
                                              opt.which_model_netD_vid,
                                              opt.n_layers_D, opt.norm, use_sigmoid, opt.init_type, self.gpu_ids)

        if not self.isTrain or opt.continue_train:
            self.load_network(self.netE, 'E', opt.which_epoch)
            self.load_network(self.netG_vid, 'G_vid', opt.which_epoch)
            self.load_network(self.netG_seq, 'G_seq', opt.which_epoch)
            if self.isTrain:
                self.load_network(self.netD_vid, 'D_vid', opt.which_epoch)
                self.load_network(self.netD_seq, 'D_seq', opt.which_epoch)

        if self.isTrain:
            # 3D Change
            # define loss functions
            self.criterionGAN = networks.GANLoss(use_lsgan=not opt.no_lsgan, tensor=self.Tensor)
            self.criterionL1 = torch.nn.L1Loss()

            # initialize optimizers
            self.schedulers = []
            self.optimizers = []
            self.optimizer_E = torch.optim.Adam(self.netE.parameters(),
                                                lr=opt.lr, betas=(opt.beta1, 0.999))
            self.optimizer_G_vid = torch.optim.Adam(self.netG_vid.parameters(),
                                                    lr=opt.lr, betas=(opt.beta1, 0.999))
            self.optimizer_G_seq = torch.optim.Adam(self.netG_seq.parameters(),
                                                    lr=opt.lr, betas=(opt.beta1, 0.999))
            self.optimizer_D_vid = torch.optim.Adam(self.netD_vid.parameters(),
                                                    lr=opt.lr, betas=(opt.beta1, 0.999))
            self.optimizer_D_seq = torch.optim.Adam(self.netD_seq.parameters(),
                                                    lr=opt.lr, betas=(opt.beta1, 0.999))
            self.optimizers.append(self.optimizer_E)
            self.optimizers.append(self.optimizer_G_vid)
            self.optimizers.append(self.optimizer_G_seq)
            self.optimizers.append(self.optimizer_D_vid)
            self.optimizers.append(self.optimizer_D_seq)

            for optimizer in self.optimizers:
                self.schedulers.append(networks.get_scheduler(optimizer, opt))

        print('---------- Networks initialized -------------')
        networks.print_network(self.netE)
        networks.print_network(self.netG_vid)
        networks.print_network(self.netG_seq)
        if self.isTrain:
            networks.print_network(self.netD_vid)
            networks.print_network(self.netD_seq)
        print('-----------------------------------------------')

    def set_input(self, inputs, is_numpy=True):
        """
        :param is_numpy: using numpy array or not
        :param inputs: a dict contains two inputs forms with key: 'video' and 'target_seq'
        :return:
        """
        ## numpy to torch tensor
        # input_A = input['A' if AtoB else 'B']
        # input_B = input['B' if AtoB else 'A']
        AtoB = self.opt.which_direction == 'AtoB'
        A = inputs['A']
        inputs['A'] = np.split(A, 2, axis=2)[0]
        inputs['B'] = np.split(A, 2, axis=2)[1]

        input_A = torch.from_numpy(inputs['A' if AtoB else 'B']).float()
        # print("======input A SIZE==== {0}".format(input_A.size()))
        input_B = torch.from_numpy(inputs['B' if AtoB else 'A']).float()
        # speedX = torch.from_numpy(inputs["speedX"])  # with the length lX = lA + lB
        seq_A = torch.from_numpy(np.split(inputs["angle"], 2, axis=1)[0]).float()*100
        seq_B = torch.from_numpy(np.split(inputs["angle"], 2, axis=1)[1]).float()*100
        # print('*' * 20 + ' set inputs, shapes:')
        # print('seq_A', seq_A.size())
        # print('seq_B', seq_B.size())




        # self.input_A.resize_(input_A.size()).copy_(input_A)
        # self.input_B.resize_(input_B.size()).copy_(input_B)
        # self.seq_A.resize_(seq_A.size()).copy_(seq_A)
        # self.seq_B.resize_(seq_B.size()).copy_(seq_B)
        
        self.input_A = Variable(input_A)
        self.input_B = Variable(input_B)
        self.seq_A = Variable(seq_A)
        self.seq_B = Variable(seq_B)

        # convert to cuda
        if self.gpu_ids and torch.cuda.is_available():
            self.input_A = self.input_A.cuda()
            self.input_B = self.input_B.cuda()
            # self.speedX = self.speedX.cuda()
            self.seq_A = self.seq_A.cuda()
            self.seq_B = self.seq_B.cuda()

        self.image_paths = inputs['A_paths' if AtoB else 'B_paths']
        self.real_A = self.input_A
        self.real_B = self.input_B

        #print(inputs["angle"])
        #print(seq_A)

        #self.seq_B = Variable(self.seq_B)
        # # numpy to torch tensor
        # if is_numpy:
        #     self.input_vid = torch.from_numpy(self.input_A)
        #     self.input_seq = torch.from_numpy(input['target_seq'])
        # else:
        #     #print(input['A'].size())
        #     self.input_vid = Variable(torch.from_numpy(input['A'])).float()
        #     #print(self.input_vid.size())
        #     self.input_seq = Variable(torch.from_numpy(input["speedX"])).float()
        # # convert to cuda
        # if self.gpu_ids and torch.cuda.is_available():
        #     self.input_vid = self.input_vid.cuda()
        #     #print(self.input_vid.size())
        #     self.input_seq = self.input_seq.cuda()

    def forward(self):
        encoded = self.netE(self.input_A)
        self.fake_B = self.netG_vid(encoded)
        self.seq_B_pred = self.netG_seq(encoded)

        # print("." * 10 + "Compare sequences" + "." * 10)
        # print(self.seq_A.data)
        # print(self.seq_A_pred.data)
        # print("." * 10 + "Compare sequences" + "." * 10)

    def backward_D(self):
        fake_AB = torch.cat((self.real_A, self.fake_B), 1).data
        fake_AB_ = Variable(fake_AB)
        fake_cat_seq = torch.cat([self.seq_A, self.seq_B_pred], 1)
        self.vid_pred_fake = self.netD_vid(fake_AB_.detach())
        self.speed_fake = self.netD_seq(fake_cat_seq.detach())
        #speed_fake = self.netD_seq(self.seq_A_pred)
        self.loss_D_fake_vid = self.criterionGAN(self.vid_pred_fake, False)
        self.loss_D_fake_seq = self.criterionGAN(self.speed_fake, False)  # fake speed


        self.loss_D_fake = self.loss_D_fake_vid + self.loss_D_fake_seq

        # Real
        real_AB = torch.cat((self.real_A, self.real_B), 1)
        real_cat_seq = torch.cat([self.seq_A, self.seq_B], 1)
        self.pred_real_vid = self.netD_vid(real_AB.detach())
        self.pred_real_seq = self.netD_seq(real_cat_seq.detach())
        self.loss_D_real_vid = self.criterionGAN(self.pred_real_vid, True)
        self.loss_D_real_seq = self.criterionGAN(self.pred_real_seq, True)

        self.loss_D_real = self.loss_D_real_vid + self.loss_D_real_seq

        # # Fake
        # # stop backprop to the generator by detaching fake seq
        # if type(self.gen_seq) != Variable:
        #     fake_seq = Variable(self.gen_seq)
        # else:
        #     fake_seq = self.gen_seq
        # pred_fake = self.netD(fake_seq.detach())
        # self.loss_D_fake = self.criterionGAN(pred_fake, False)
        #
        # # Real
        # label_size = list(self.input_seq.size())
        # label_size[2] = 1
        # pred_real = Variable(torch.ones(label_size)).cuda()
        # self.loss_D_real = self.criterionGAN(pred_real, True)

        # Combined loss
        self.loss_D = (self.loss_D_fake + self.loss_D_real) * 0.5

        self.loss_D.backward(retain_graph=True)

    def backward_G(self):

        # First, G(A) should fake the discriminator
        fake_AB = torch.cat((self.real_A, self.fake_B), 1)
        pred_vid_fake = self.netD_vid(fake_AB)
        fake_cat_seq = torch.cat([self.seq_A, self.seq_B_pred], 1)
        pred_speed_fake = self.netD_seq(fake_cat_seq)
        #self.loss_G_GAN = self.criterionGAN(pred_vid_fake, True) + \
        #                  self.criterionGAN(pred_speed_fake, True)
        self.loss_G_GAN_vid = self.criterionGAN(pred_vid_fake, True)
        self.loss_G_GAN_vid.backward(retain_graph=True)
        self.loss_G_GAN_seq = self.criterionGAN(pred_speed_fake, True)
        self.loss_G_GAN_seq.backward(retain_graph=True)
        # Second, G(A) = B
        self.loss_G_L1_vid = self.criterionL1(self.fake_B, self.real_B) * self.opt.lambda_A
        self.loss_G_L1_seq = self.criterionL1(self.seq_B_pred, self.seq_B) * self.opt.lambda_A
        #self.loss_G_L1 = self.loss_G_L1_vid + self.loss_G_L1_seq
        self.loss_G_L1_vid.backward(retain_graph=True)
        self.loss_G_L1_seq.backward(retain_graph=True)

        self.loss_G_GAN = self.loss_G_GAN_vid + self.loss_G_GAN_seq

        self.loss_G_L1 = self.loss_G_L1_vid + self.loss_G_L1_seq

        #loss_G_vid= loss_G_GAN_vid + self.loss_G_L1_vid
        #loss_G_seq = loss_G_GAN_seq + self.loss_G_L1_seq
        #loss_G_seq.backward(retain_graph=True)
        #loss_G_vid.backward()#retain_graph=True)

        # action
        # self.action_loss = self.criterionL2(self.action,self.action_prediction)
        #self.loss_G = self.loss_G_GAN + self.loss_G_L1  # +self.action_loss
        #self.loss_G.backward(retain_graph=True)

        # First, G(A) should fool the discriminator
        # pred_fake = self.netD(self.gen_seq)
        # self.loss_G_GAN = self.criterionGAN(pred_fake, True)
        #
        # # Second, G(A) = B
        # self.loss_G_L1 = self.criterionL1(self.gen_seq, self.input_seq) * 10.0  # opt.lambda_A
        #
        # self.loss_G = self.loss_G_GAN + self.loss_G_L1
        #
        # self.loss_G.backward()
        # return mse loss, for print
        return self.netG_seq.batch_mse_loss(self.input_A, self.seq_B)

    def pretrain_G_step(self):
        # print(self.input_vid.size())
        g_loss = self.netG.batch_mse_loss(self.input_A, self.seq_B)
        self.seq_B_pred = self.netG.gen_seq
        self.optimizer_G.zero_grad()
        g_loss.backward(retain_graph=True)
        self.optimizer_G.step()
        return g_loss

    def pretrain_D_seq(self):
        label_size = list(self.seq_B.size())
        label_size[2] = 1
        target_speed_real = Variable(torch.ones(label_size).resize_(label_size[0], label_size[1]))
        target_speed_fake = Variable(torch.zeros(label_size).resize_(label_size[0], label_size[1]))
        self.forward()

        # warnings.warn("Using a target size ({}) that is different to the input size ({}) is deprecated. "
        #               "Please ensure they have the same size.".format(self.seq_B.size(), target_real.size()))

        d_loss = self.netD_seq.batch_bce_loss(self.seq_B.cuda(), target_speed_real.cuda())
        d_loss += self.netD_vid.batch_bce_loss(self.seq_B_pred.detach().cuda(), target_speed_fake.cuda())
        self.optimizer_D_seq.zero_grad()
        d_loss.backward()
        self.optimizer_D_seq.step()
        return d_loss

    def optimize_parameters(self):
        self.forward()

        self.optimizer_D_vid.zero_grad()
        self.optimizer_D_seq.zero_grad()
        self.backward_D()
        self.optimizer_D_vid.step()
        self.optimizer_D_seq.step()

        self.optimizer_E.zero_grad()
        self.optimizer_G_vid.zero_grad()
        self.optimizer_G_seq.zero_grad()
        g_mse_loss = self.backward_G()
        self.optimizer_G_vid.step()
        self.optimizer_G_seq.step()
        self.optimizer_E.step()

        return g_mse_loss

    def get_current_errors(self):
        return OrderedDict([('G_GAN', self.loss_G_GAN.data[0]),
                            ('self.loss_G_GAN_vid', self.loss_G_GAN_vid.data[0]),
                            ('self.loss_G_GAN_seq', self.loss_G_GAN_seq.data[0]),
                            ('G_L1', self.loss_G_L1.data[0]),
                            ('self.loss_G_L1_vid', self.loss_G_L1_vid.data[0]),
                            ('self.loss_G_L1_seq', self.loss_G_L1_seq.data[0]),
                            ('D_real', self.loss_D_real.data[0]),
                            ('self.loss_D_real_vid', self.loss_D_real_vid.data[0]),
                            ('self.loss_D_real_seq', self.loss_D_real_seq.data[0]),
                            ('D_fake', self.loss_D_fake.data[0]),
                            ('self.loss_D_fake_vid', self.loss_D_fake_vid.data[0]),
                            ('self.loss_D_fake_seq', self.loss_D_fake_seq.data[0])
                            ])


    def get_current_visuals(self):
        if self.dataset_mode == 'v':
            real_A = util.tensor2vid(self.real_A.data)
            fake_B = util.tensor2vid(self.fake_B.data)
            real_B = util.tensor2vid(self.real_B.data)
        else:
            real_A = util.tensor2im(self.real_A.data)
            fake_B = util.tensor2im(self.fake_B.data)
            real_B = util.tensor2im(self.real_B.data)
        return OrderedDict([('real_A', real_A), ('fake_B', fake_B), ('real_B', real_B)])



#    def get_current_visuals(self):
#       return OrderedDict([('real_A', self.input_A), ('fake_B', self.fake_B),
#                            ('real_B', self.seq_A), ('fake_seq', self.seq_A_pred)])

    def save(self, label):
        self.save_network(self.netG, 'G', label, self.gpu_ids)
        self.save_network(self.netD_vid, 'D_vid', label, self.gpu_ids)
        self.save_network(self.netD_seq, 'D_seq', label, self.gpu_ids)
