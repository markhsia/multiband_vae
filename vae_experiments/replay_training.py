import copy
import numpy as np
import torch
import torch.functional as F
from torch import optim

from vae_experiments.vae_utils import generate_previous_data
from vae_experiments.training_functions import loss_fn


def train_with_replay(args, local_vae, task_loader, task_id, class_table):
    optimizer = torch.optim.Adam(local_vae.parameters(), lr=0.001)
    scheduler = optim.lr_scheduler.ExponentialLR(optimizer, gamma=0.99)
    frozen_model = copy.deepcopy(local_vae.decoder)
    frozen_model.eval()
    local_vae.train()
    table_tmp = torch.zeros(class_table.size(1), dtype=torch.long)

    for epoch in range(args.gen_ae_epochs):
        losses = []
        for iteration, batch in enumerate(task_loader):
            x = batch[0].to(local_vae.device)
            y = batch[1].to(local_vae.device)

            if epoch == 0:
                class_counter = torch.unique(y, return_counts=True)
                table_tmp[class_counter[0]] += class_counter[1].cpu()

            if task_id > 0:
                recon_prev, recon_classes = generate_previous_data(frozen_model, class_table=class_table,
                                                                   n_tasks=task_id, n_img=task_id * x.size(0))
                x = torch.cat([x, recon_prev], dim=0)
                y = torch.cat([y.view(-1), recon_classes.to(local_vae.device)], dim=0)

            recon_x, mean, log_var, z = local_vae(x, task_id, y)

            loss = loss_fn(recon_x, x, mean, log_var)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            losses.append(loss.item())
        scheduler.step()
        #     print("lr:",scheduler.get_lr())
        if (epoch % 10 == 0):
            print("Epoch: {}/{}, loss: {}".format(epoch, args.gen_ae_epochs, np.mean(losses)))
    return local_vae.decoder, table_tmp