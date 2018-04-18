#!/usr/bin/python3
# -*- coding: utf-8 -*-


class KSException(BaseException):
    pass


class KSError(KSException):
    pass


class KSNotFound(KSError):
    pass
