import torch
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from torch import optim

from vae_experiments.lap_loss import LapLoss
from vae_experiments.vae_utils import *
import copy


def loss_fn(y, x_target, mu, sigma, lap_loss_fn=None):
    marginal_likelihood = F.binary_cross_entropy(y, x_target, reduction='sum') / y.size(0)

    # KL_divergence = 0.5 * torch.sum(
    #     torch.pow(mu, 2) +
    #     torch.pow(sigma, 2) -
    #     torch.log(1e-8 + torch.pow(sigma, 2)) - 1
    # ).sum() / y.size(0)
    KL_divergence = -0.5 * torch.sum(1 + sigma - mu.pow(2) - sigma.exp()) / y.size(0)
    if lap_loss_fn:
        lap_loss = lap_loss_fn(y, x_target)
        loss = marginal_likelihood + x_target[0].size()[1] * x_target[0].size()[1] * lap_loss + KL_divergence
    else:
        loss = marginal_likelihood + KL_divergence

    return loss


def train_local_generator(local_vae, task_loader, task_id, n_classes, n_epochs=100, use_lap_loss=False):
    optimizer = torch.optim.Adam(local_vae.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ExponentialLR(optimizer, gamma=0.99)
    table_tmp = torch.zeros(n_classes, dtype=torch.long)
    lap_loss = LapLoss(device=local_vae.device) if use_lap_loss else None

    for epoch in range(n_epochs):
        losses = []
        for iteration, batch in enumerate(task_loader):

            x = batch[0].to(local_vae.device)
            y = batch[1].to(local_vae.device)
            recon_x, mean, log_var, z = local_vae(x, task_id, y)

            loss = loss_fn(recon_x, x, mean, log_var, lap_loss)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            losses.append(loss.item())
            if epoch == 0:
                class_counter = torch.unique(y, return_counts=True)
                table_tmp[class_counter[0]] += class_counter[1].cpu()
        scheduler.step()
        #     print("lr:",scheduler.get_lr())
        #     print(iteration,len(task_loader))
        if epoch % 1 == 0:
            print("Epoch: {}/{}, loss: {}".format(epoch, n_epochs, np.mean(losses)))
    return table_tmp


def train_global_decoder(curr_global_decoder, local_vae, task_id, class_table, n_epochs=100, n_iterations=30,
                         batch_size=1000):
    global_decoder = copy.deepcopy(curr_global_decoder)
    optimizer = torch.optim.Adam(global_decoder.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ExponentialLR(optimizer, gamma=0.99)
    criterion = nn.BCELoss(reduction='sum')
    class_samplers = prepare_class_samplres(task_id + 1, class_table)

    for epoch in range(n_epochs):
        losses = []
        for iteration in range(n_iterations):

            # Building dataset from previous global model and local model
            with torch.no_grad():
                z_prev = torch.randn([batch_size * task_id, local_vae.latent_size]).to(curr_global_decoder.device)
                task_ids_prev = np.repeat(list(range(task_id)), [batch_size])
                sampled_classes = []
                for i in range(task_id + 1):  ## Including current class
                    sampled_classes.append(class_samplers[i].sample([batch_size]))
                sampled_classes_prev = torch.cat(sampled_classes[:-1])
                recon_prev = curr_global_decoder(z_prev, task_ids_prev, sampled_classes_prev)
                # @TODO Check if training with same random variables for both local and previous global model works better
                z_local = torch.randn([batch_size, local_vae.latent_size]).to(curr_global_decoder.device)
                task_ids_local = np.zeros([batch_size]) + task_id
                recon_local = local_vae.decoder(z_local, task_ids_local, sampled_classes[-1])

            z_concat = torch.cat([z_prev, z_local])
            task_ids_concat = np.concatenate([task_ids_prev, task_ids_local]).reshape(-1, 1)
            recon_concat = torch.cat([recon_prev, recon_local])

            global_recon = global_decoder(z_concat, task_ids_concat, torch.cat(sampled_classes))
            loss = criterion(global_recon, recon_concat)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            losses.append(loss.item())
        scheduler.step()
        #     print("lr:",scheduler.get_lr())
        if (epoch % 1 == 0):
            print("Epoch: {}/{}, loss: {}".format(epoch, n_epochs, np.mean(losses)))
    return global_decoder
