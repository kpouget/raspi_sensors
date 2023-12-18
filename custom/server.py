#! /usr/bin/env python3

import json
import sys
import os
import yaml

import datetime
import bottle
import prometheus_client
import prometheus_client.parser

METRICS_FILE_YAML = "out/metrics.yaml"
METRICS_FILE = "out/metrics.txt"
CREATE_LABELS_COUNT = 3

published_metrics = {}
top_metrics = {}
yaml_metrics = {}


@bottle.route('/static/<filepath:re:.*\.css>')
def css(filepath):
    return bottle.static_file(filepath, root="static/css")


def update_metric(metric_key, update_value, increase=True):
    metric, entry = published_metrics[metric_key]
    current_value = entry.get("value") or 0

    new_value = float(update_value)
    if increase:
        new_value += current_value

    metric.set(new_value)
    entry["last_update"]["date"] = datetime.datetime.now().strftime('%Y-%m-%d à %H:%M')
    entry["last_update"]["value"] = float(update_value)
    entry["value"] = new_value

    with open(METRICS_FILE_YAML, "w") as f:
        if not yaml_metrics:
            raise Exception("yaml is empty ...")
        print(yaml.dump(yaml_metrics), file=f)

    return f"{metric._documentation} [{metric_key}] +{update_value}{entry['units']} --> {new_value}{entry['units']}", True


def new_metric(forms):
    name = forms["__new__.name"]
    docu = forms["__new__.documentation"]
    units = forms["__new__.units"]

    if docu == "exit":
        sys.stderr.close()
        return "Closing", False

    if docu == "delete":
        try:
            metric, entry = published_metrics.pop(name)
        except KeyError:
            return f"Métrique {name} n'existe pas :/", False
        # prometheus_client.registry.REGISTRY.unregister(metric)

        yaml_metrics[metric.name].pop(entry)

        return f"Métrique {name} supprimée", True

    labels = {}
    for label_id in range(CREATE_LABELS_COUNT):
        label_name = forms.get(f"__new__.label{label_id}")
        if not label_name: continue
        label_value = forms.get(f"__new__.labelvalue{label_id}", "no value")
        labels[label_name] = label_value

    try:
        metric = top_metrics[name]
    except KeyError:
        metric = prometheus_client.Gauge(name, docu, labels.keys())
        top_metrics[name] = metric

    if labels:
        metric = metric.labels(*labels.values())

    metric.set(0)

    if name not in yaml_metrics:
        yaml_metrics[name] = dict(
            documentation=docu,
            entries=[],
        )

    entry = dict(
        labels=labels,
        last_update=dict(date=None, value=None),
        value=0,
        units=units,
    )

    yaml_metrics[name]["entries"].append(entry)

    publish_metric(metric, entry)

    with open(METRICS_FILE_YAML, "w") as f:
        if not yaml_metrics:
            raise Exception("yaml is empty ...")
        print(yaml.dump(yaml_metrics), file=f)


    return f"Métrique {name}{labels} crée :)", True


def publish_metric(metric, entry):
    label_id = "-".join([f"{k}_{v}" for k, v in zip(metric._labelnames, metric._labelvalues)])

    published_metrics[f"{metric._name}--{label_id}"] = metric, entry


@bottle.route('/', method=["POST", "GET"])
def index():
    if bottle.request.forms:
        metric_key = bottle.request.forms["what"]
        if metric_key == "__new__":
            msg, save = new_metric(bottle.request.forms)
        else:
            new_value = bottle.request.forms[metric_key]
            do_increase = bottle.request.forms.get("__increase__", "true") == "true"
            msg, save = update_metric(metric_key, new_value, increase=do_increase)

        if save:
            prometheus_client.write_to_textfile(METRICS_FILE, prometheus_client.registry.REGISTRY)

    else:
        msg = None

    return bottle.template("index", published_metrics=published_metrics.items(), msg=msg, CREATE_LABELS_COUNT=CREATE_LABELS_COUNT)


def load_metrics():
    with open(METRICS_FILE_YAML) as f:
        global yaml_metrics
        yaml_metrics = yaml.safe_load(f)

    for metric_name, metric_props in yaml_metrics.items():
        metric_labels = set()

        for entry in metric_props["entries"]:
            metric_labels |= entry["labels"].keys()

        metric = prometheus_client.Gauge(metric_name, metric_props["documentation"],
                                         list(metric_labels))
        top_metrics[metric_name] = metric
        for entry in metric_props["entries"]:
            if entry["labels"]:
                full_metric = metric.labels(*entry["labels"].values())
            full_metric.set(entry.get("value") or 0)

            publish_metric(full_metric, entry)


@bottle.route('/metrics')
def metrics():
    return bottle.static_file(METRICS_FILE, root=".")


if __name__ == "__main__":
    load_metrics()
    for metric, entry in published_metrics.values():
        labels = dict(zip(metric._labelnames, metric._labelvalues))
        print(metric, metric._documentation, labels)

    bottle.run(host='localhost', port=int(os.environ.get("BOTTLE_PORT", 8080)), reloader=True)
